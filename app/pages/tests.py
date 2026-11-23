from django.test import TestCase
from django.urls import reverse
from datetime import timedelta
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, override_settings
from django.utils import timezone

from .models import Content, FAQ, NotificationDelivery, Subscriber
from .notifications import subscription_url


class HomepageTests(TestCase):
    def test_health_reports_dependency_failures_without_details(self):
        self.assertJSONEqual(self.client.get(reverse("health")).content, {"status": "ok"})
        with patch("pages.views.cache.get", side_effect=RuntimeError("private connection details")):
            response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 503)
        self.assertJSONEqual(response.content, {"status": "unavailable"})

    def test_home_keeps_design_and_loads_local_libraries(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Stronger connections.")
        self.assertContains(response, "castries-harbour.jpg")
        self.assertContains(response, "vendor/alpine-3.14.9.min.js")
        self.assertContains(response, "vendor/htmx-2.0.11.min.js")
        self.assertContains(response, 'x-data="ministrySite"')
        self.assertContains(response, 'class="update-card"', count=3)

    def test_search_returns_fragment_for_htmx(self):
        response = self.client.get(reverse("search"), {"q": "DRIVER vehicle"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Driver and vehicle services")
        self.assertNotContains(response, "<!doctype html>")
        self.assertNotContains(response, "Ports and connectivity")
        self.assertIn("HX-Request", response.headers["Vary"])

    def test_search_has_empty_state(self):
        for query in ("", "   ", "no-such-section"):
            with self.subTest(query=query):
                response = self.client.get(reverse("search"), {"q": query}, HTTP_HX_REQUEST="true")
                self.assertContains(response, "No matching sections")

    def test_search_without_htmx_renders_full_page_and_opens_panel(self):
        response = self.client.get(reverse("search"), {"q": "roads"})
        self.assertContains(response, "<!doctype html>")
        self.assertContains(response, "Roads, infrastructure and public works")
        self.assertContains(response, 'x-init="searchOpen = true"')

    def test_query_is_escaped_and_bounded(self):
        response = self.client.get(reverse("search"), {"q": '\"><script>alert(1)</script>'})
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, "&lt;script&gt;")
        response = self.client.get(reverse("search"), {"q": "a" * 500})
        self.assertEqual(len(response.context["query"]), 200)

    def test_update_filters_render_only_matching_cards(self):
        for category, count in (("all", 3), ("notice", 2), ("publication", 1)):
            with self.subTest(category=category):
                response = self.client.get(reverse("updates"), {"category": category}, HTTP_HX_REQUEST="true")
                self.assertContains(response, 'class="update-card"', count=count)
                self.assertNotContains(response, "<!doctype html>")
                self.assertContains(response, 'aria-current="true"', count=1)
                self.assertIn("HX-Request", response.headers["Vary"])

    def test_invalid_filter_falls_back_to_all(self):
        response = self.client.get(reverse("updates"), {"category": "invalid"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.context["category"], "all")
        self.assertContains(response, 'class="update-card"', count=3)

    def test_filter_without_htmx_returns_full_page(self):
        response = self.client.get(reverse("home"), {"category": "publication"})
        self.assertContains(response, "<!doctype html>")
        self.assertContains(response, 'class="update-card"', count=1)
        response = self.client.get(reverse("updates"), {"category": "notice"})
        self.assertContains(response, "<!doctype html>")
        self.assertContains(response, 'class="update-card"', count=2)

    def test_endpoints_are_read_only(self):
        for route in ("home", "search", "updates"):
            with self.subTest(route=route):
                self.assertEqual(self.client.post(reverse(route)).status_code, 405)


class PublishingTests(TestCase):
    def make_content(self, **kwargs):
        values = dict(title="Bridge improvement programme", slug="bridge-improvement", category="project",
                      summary="Safer bridge connections.", body="First paragraph.\n\nSecond paragraph.", is_published=True)
        values.update(kwargs)
        return Content.objects.create(**values)

    def test_draft_and_scheduled_items_are_not_public_or_searchable(self):
        for kwargs in ({"is_published": False}, {"published_at": timezone.now() + timedelta(days=1)}):
            item = self.make_content(**kwargs)
            self.assertNotContains(self.client.get(reverse("home")), item.title)
            self.assertEqual(self.client.get(item.get_absolute_url()).status_code, 404)
            self.assertNotContains(self.client.get(reverse("search"), {"q": "bridge"}, HTTP_HX_REQUEST="true"), item.title)
            item.delete()

    def test_all_categories_publish_to_their_sections_and_search(self):
        for category in ("news", "notice", "publication", "project"):
            item = self.make_content(slug=category, category=category, title=f"Bridge {category}")
            response = self.client.get(reverse("home"))
            self.assertContains(response, item.title)
            self.assertContains(self.client.get(item.get_absolute_url()), "Second paragraph.")
            result = self.client.get(reverse("search"), {"q": item.title}, HTTP_HX_REQUEST="true")
            self.assertContains(result, item.get_absolute_url())
            if category != "project":
                filtered = self.client.get(reverse("updates"), {"category": category}, HTTP_HX_REQUEST="true")
                self.assertContains(filtered, item.title)

    def test_content_is_escaped_and_hidden_faq_is_excluded(self):
        item = self.make_content(body='<script>alert("test")</script>')
        self.assertNotContains(self.client.get(item.get_absolute_url()), '<script>alert("test")</script>')
        FAQ.objects.create(question="Hidden FAQ", answer="Private draft", is_published=False)
        self.assertNotContains(self.client.get(reverse("home")), "Hidden FAQ")

    def test_pdf_upload_validation_and_download_link(self):
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            item = self.make_content(document=SimpleUploadedFile("policy.pdf", b"%PDF-1.4 test", content_type="application/pdf"))
            item.full_clean()
            self.assertContains(self.client.get(item.get_absolute_url()), "Download document (PDF)")
            item.document = SimpleUploadedFile("script.html", b"<script>bad</script>")
            with self.assertRaises(ValidationError):
                item.full_clean()
            item.document = SimpleUploadedFile("large.pdf", b"x" * (10 * 1024 * 1024 + 1))
            with self.assertRaises(ValidationError):
                item.full_clean()



@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", SITE_URL="http://testserver")
class SubscriptionTests(TestCase):
    def subscribe(self, **kwargs):
        data = {"email": "Person@Example.com", "topics": ["news", "publication"], "consent": "on"}
        data.update(kwargs)
        return self.client.post(reverse("subscribe"), data)

    def url(self, subscriber, action):
        return subscription_url(subscriber, action).replace("http://testserver", "")

    def test_confirmation_consent_and_unsubscribe_lifecycle(self):
        self.assertRedirects(self.subscribe(), reverse("home") + "#subscribe")
        subscriber = Subscriber.objects.get(email="person@example.com")
        self.assertFalse(subscriber.is_active)
        self.assertEqual(len(mail.outbox), 1)
        confirm = self.url(subscriber, "confirm_subscription")
        self.assertIn(confirm, mail.outbox[0].body)
        self.client.get(confirm)
        subscriber.refresh_from_db()
        self.assertFalse(subscriber.is_active)  # Email scanners must not activate subscriptions.
        self.assertContains(self.client.post(confirm), "You’re subscribed.")
        subscriber.refresh_from_db()
        self.assertEqual(subscriber.topics, ["news", "publication"])
        self.assertTrue(subscriber.is_active)
        unsubscribe = self.url(subscriber, "unsubscribe")
        self.client.get(unsubscribe)
        subscriber.refresh_from_db()
        self.assertTrue(subscriber.is_active)
        self.assertContains(self.client.post(unsubscribe), "You’re unsubscribed.")
        subscriber.refresh_from_db()
        self.assertFalse(subscriber.is_active)
        self.assertEqual(self.client.post(confirm).status_code, 400)

    def test_validation_requires_email_topics_and_consent(self):
        for data in ({"email": "bad"}, {"topics": []}, {"consent": ""}):
            response = self.subscribe(**data)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Subscriber.objects.count(), 0)

    def test_repeat_requests_cooldown_and_honeypot(self):
        self.subscribe()
        self.subscribe()
        self.assertEqual(Subscriber.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.subscribe(email="bot@example.com", website="spam")
        self.assertEqual(Subscriber.objects.count(), 1)

    def test_topic_changes_require_reconfirmation(self):
        self.subscribe()
        subscriber = Subscriber.objects.get()
        self.client.post(self.url(subscriber, "confirm_subscription"))
        Subscriber.objects.update(requested_at=timezone.now() - timedelta(minutes=6))
        self.subscribe(topics=["notice"])
        subscriber.refresh_from_db()
        self.assertEqual(subscriber.topics, ["news", "publication"])
        self.client.post(self.url(subscriber, "confirm_subscription"))
        subscriber.refresh_from_db()
        self.assertEqual(subscriber.topics, ["notice"])

    def test_invalid_and_expired_tokens(self):
        self.assertEqual(self.client.get(reverse("confirm_subscription", args=["bad-token"])).status_code, 400)
        self.subscribe()
        url = self.url(Subscriber.objects.get(), "confirm_subscription")
        import time
        with patch("django.core.signing.time.time", return_value=time.time() + 49 * 60 * 60):
            self.assertEqual(self.client.post(url).status_code, 400)

    def test_mail_failure_reports_error_and_allows_retry(self):
        with patch("pages.views.send_mail", side_effect=OSError("offline")):
            self.assertEqual(self.subscribe().status_code, 503)
        self.assertEqual(Subscriber.objects.count(), 0)
        self.assertEqual(self.subscribe().status_code, 302)

    def test_csrf_required_for_subscription_actions(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("subscribe"), {}).status_code, 403)

    def test_delivery_targets_confirmed_topics_once_and_retries_failures(self):
        yesterday = timezone.now() - timedelta(days=1)
        subscriber = Subscriber.objects.create(email="yes@example.com", topics=["news"], is_active=True, confirmed_at=yesterday)
        Subscriber.objects.create(email="pending@example.com", topics=["news"])
        Subscriber.objects.create(email="other@example.com", topics=["project"], is_active=True, confirmed_at=yesterday)
        Subscriber.objects.create(email="unsubscribed@example.com", topics=["news"], is_active=False, confirmed_at=yesterday)
        item = Content.objects.create(title="New road", slug="new-road", category="news", summary="Road update",
            body="Details", is_published=True, notify_subscribers=True, published_at=timezone.now() - timedelta(hours=1))
        Subscriber.objects.create(email="new@example.com", topics=["news"], is_active=True, confirmed_at=timezone.now())
        call_command("send_notifications", dry_run=True, stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(NotificationDelivery.objects.count(), 0)
        from django.core.management.base import CommandError
        with patch("pages.management.commands.send_notifications.send_mail", side_effect=OSError("offline")):
            with self.assertRaises(CommandError):
                call_command("send_notifications", stdout=StringIO(), stderr=StringIO())
        call_command("send_notifications", stdout=StringIO())
        call_command("send_notifications", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [subscriber.email])
        self.assertIn(item.get_absolute_url(), mail.outbox[0].body)
        self.assertIn(self.url(subscriber, "unsubscribe"), mail.outbox[0].body)
        self.assertIsNotNone(NotificationDelivery.objects.get().sent_at)

    def test_drafts_future_items_and_disabled_notifications_send_nothing(self):
        Subscriber.objects.create(email="yes@example.com", topics=["news"], is_active=True,
            confirmed_at=timezone.now() - timedelta(days=1))
        for index, extra in enumerate([{"is_published": False}, {"published_at": timezone.now() + timedelta(days=1)}, {"notify_subscribers": False}]):
            values = {"title": "Road", "slug": f"road-{index}", "category": "news", "summary": "Update", "body": "Details", "is_published": True, "notify_subscribers": True}
            values.update(extra)
            Content.objects.create(**values)
        call_command("send_notifications", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

from datetime import timedelta
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Content, FAQ, Subscriber


class StaffWorkspaceTests(TestCase):
    def setUp(self):
        self.editor = get_user_model().objects.create_user(username="editor", password="staff-test-password", is_staff=True)
        self.editor.groups.add(Group.objects.get(name="Content editors"))
        self.item = Content.objects.create(title="Road programme", slug="road-programme", category="project",
            summary="Road improvements", body="Detailed programme", is_published=False)
        self.faq = FAQ.objects.create(question="A new question?", answer="A clear answer.")

    def content_data(self, **extra):
        data = {"title": "Bridge update", "slug": "", "category": "news", "summary": "Bridge improvements",
            "body": "A detailed update", "published_at": "2026-01-01T10:00"}
        data.update(extra)
        return data

    def test_login_logout_and_safe_redirects(self):
        response = self.client.get(reverse("staff_content_list"))
        self.assertRedirects(response, reverse("staff_login") + "?next=" + reverse("staff_content_list"))
        get_user_model().objects.create_user(username="visitor", password="test-password")
        self.assertContains(self.client.post(reverse("staff_login"), {"username": "visitor", "password": "test-password"}), "does not have staff access")
        response = self.client.post(reverse("staff_login"), {"username": "editor", "password": "staff-test-password", "next": "https://untrusted.example/"})
        self.assertRedirects(response, reverse("staff_dashboard"))
        self.assertEqual(self.client.get(reverse("staff_logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("staff_logout")), reverse("staff_login"))
        self.assertEqual(self.client.get(reverse("staff_dashboard")).status_code, 302)

    def routes(self):
        return [("staff_dashboard", []), ("staff_content_list", []), ("staff_content_create", []),
            ("staff_content_edit", [self.item.pk]), ("staff_content_preview", [self.item.pk]),
            ("staff_content_delete", [self.item.pk]), ("staff_faq_list", []), ("staff_faq_create", []),
            ("staff_faq_edit", [self.faq.pk]), ("staff_faq_delete", [self.faq.pk])]

    def test_all_routes_enforce_staff_and_permissions(self):
        for is_staff in (False, True):
            user = get_user_model().objects.create_user(username=f"unassigned-{is_staff}", is_staff=is_staff)
            self.client.force_login(user)
            for route, args in self.routes() + [("staff_subscribers", [])]:
                with self.subTest(is_staff=is_staff, route=route):
                    self.assertEqual(self.client.get(reverse(route, args=args)).status_code, 403)
                    self.assertEqual(self.client.post(reverse(route, args=args), {}).status_code, 403)
        self.assertTrue(Content.objects.filter(pk=self.item.pk).exists())

    def test_editor_views_render_without_admin_and_are_not_cached(self):
        self.client.force_login(self.editor)
        for route, args in self.routes():
            with self.subTest(route=route):
                response = self.client.get(reverse(route, args=args))
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response.headers["Cache-Control"])
                self.assertNotContains(response, "admin/css")
        self.assertEqual(self.client.get(reverse("staff_subscribers")).status_code, 403)
        self.assertContains(self.client.get(reverse("home")), 'href="/staff/">Staff sign in')

    def test_create_each_category_and_generate_unique_slugs(self):
        self.client.force_login(self.editor)
        for category in Content.Category.values:
            self.assertRedirects(self.client.post(reverse("staff_content_create"), self.content_data(category=category)), reverse("staff_content_list"))
        items = Content.objects.filter(title="Bridge update")
        self.assertEqual(items.count(), 4)
        self.assertEqual(len({item.slug for item in items}), 4)
        for item in items:
            self.assertFalse(item.is_published)
            self.assertEqual(self.client.get(item.get_absolute_url()).status_code, 404)
            self.assertContains(self.client.get(reverse("staff_content_preview", args=[item.pk])), item.title)

    def test_edit_publish_schedule_and_unpublish(self):
        self.client.force_login(self.editor)
        url = reverse("staff_content_edit", args=[self.item.pk])
        self.assertRedirects(self.client.post(url, self.content_data(is_published="on", notify_subscribers="on")), reverse("staff_content_list"))
        self.item.refresh_from_db()
        self.assertTrue(self.item.notify_subscribers)
        self.assertContains(self.client.get(self.item.get_absolute_url()), "Bridge update")
        self.assertEqual(timezone.localtime(self.item.published_at).hour, 10)
        future = timezone.localtime(timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        self.client.post(url, self.content_data(is_published="on", published_at=future))
        self.item.refresh_from_db()
        self.assertEqual(self.item.publication_status, "Scheduled")
        self.assertEqual(self.client.get(self.item.get_absolute_url()).status_code, 404)
        self.client.post(url, self.content_data())
        self.item.refresh_from_db()
        self.assertEqual(self.item.publication_status, "Draft")

    def test_form_validation_and_pdf_upload(self):
        self.client.force_login(self.editor)
        url = reverse("staff_content_create")
        response = self.client.post(url, self.content_data(title="", slug=self.item.slug))
        self.assertContains(response, "Please correct the fields below")
        self.assertEqual(Content.objects.count(), 1)
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            bad = self.client.post(url, self.content_data(document=SimpleUploadedFile("bad.html", b"bad")))
            self.assertContains(bad, "not allowed")
            good = self.client.post(url, self.content_data(document=SimpleUploadedFile("report.pdf", b"%PDF-1.4 test")))
            self.assertRedirects(good, reverse("staff_content_list"))
            self.assertTrue(Content.objects.get(title="Bridge update").document.name.endswith("report.pdf"))

    def test_content_search_filters_and_pagination(self):
        self.client.force_login(self.editor)
        for n in range(17):
            Content.objects.create(title=f"Bridge {n}", slug=f"bridge-{n}", category="news", summary="Summary", body="Details", is_published=True)
        response = self.client.get(reverse("staff_content_list"), {"q": "Bridge", "category": "news", "status": "published"})
        self.assertEqual(response.context["page_obj"].paginator.count, 17)
        self.assertEqual(len(response.context["page_obj"]), 15)
        self.assertNotContains(response, "Road programme")
        self.assertEqual(len(self.client.get(reverse("staff_content_list"), {"page": 2}).context["page_obj"]), 3)
        response = self.client.get(reverse("staff_content_list"), {"status": "draft"})
        self.assertContains(response, "Road programme")
        self.assertNotContains(response, "Bridge 1")

    def test_faq_create_edit_hide_and_confirm_delete(self):
        self.client.force_login(self.editor)
        data = {"question": "How do I get updates?", "answer": "Subscribe online.", "order": 9, "is_published": "on"}
        self.assertRedirects(self.client.post(reverse("staff_faq_create"), data), reverse("staff_faq_list"))
        faq = FAQ.objects.get(question=data["question"])
        self.assertContains(self.client.get(reverse("home")), faq.question)
        data.pop("is_published")
        self.client.post(reverse("staff_faq_edit", args=[faq.pk]), data)
        self.assertNotContains(self.client.get(reverse("home")), faq.question)
        url = reverse("staff_faq_delete", args=[faq.pk])
        self.client.get(url)
        self.assertTrue(FAQ.objects.filter(pk=faq.pk).exists())
        self.assertRedirects(self.client.post(url), reverse("staff_faq_list"))
        self.assertFalse(FAQ.objects.filter(pk=faq.pk).exists())

    def test_content_delete_and_write_forms_require_post_and_csrf(self):
        self.client.force_login(self.editor)
        url = reverse("staff_content_delete", args=[self.item.pk])
        self.assertContains(self.client.get(url), "Delete permanently")
        self.assertTrue(Content.objects.filter(pk=self.item.pk).exists())
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.editor)
        self.assertEqual(client.post(url).status_code, 403)
        self.assertEqual(client.post(reverse("staff_content_create"), self.content_data()).status_code, 403)
        self.assertRedirects(self.client.post(url), reverse("staff_content_list"))
        self.assertFalse(Content.objects.filter(pk=self.item.pk).exists())

    def test_view_only_user_cannot_edit_or_delete(self):
        user = get_user_model().objects.create_user(username="viewer", is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename="view_content", content_type__app_label="pages"))
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse("staff_content_list")), self.item.title)
        self.assertEqual(self.client.post(reverse("staff_content_edit", args=[self.item.pk]), self.content_data()).status_code, 403)
        self.assertEqual(self.client.post(reverse("staff_content_delete", args=[self.item.pk])).status_code, 403)

    def test_subscribers_restricted_to_authorized_users_and_content_admin_removed(self):
        owner = get_user_model().objects.create_superuser(username="owner", password="test-password", email="owner@example.com")
        self.client.force_login(owner)
        Subscriber.objects.create(email="confirmed@example.com", topics=["news"], is_active=True, confirmed_at=timezone.now())
        Subscriber.objects.create(email="pending@example.com", topics=["news"])
        response = self.client.get(reverse("staff_subscribers"), {"q": "confirmed"})
        self.assertContains(response, "confirmed@example.com")
        self.assertNotContains(response, "pending@example.com")
        self.assertEqual(response.context["active_count"], 1)
        self.assertEqual(self.client.get("/admin/pages/content/").status_code, 404)

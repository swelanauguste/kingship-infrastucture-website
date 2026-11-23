import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.core.mail import send_mail
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.vary import vary_on_headers

from .content import SEARCH_SECTIONS, UPDATE_FILTERS, UPDATES
from .forms import SubscriptionForm
from .models import Content, FAQ, Subscriber
from .notifications import subscription_url

logger = logging.getLogger(__name__)


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        cache.set("healthcheck", "ok", 30)
        if cache.get("healthcheck") != "ok":
            raise RuntimeError("Cache unavailable")
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def homepage_context(request):
    category = request.GET.get("category", "all")
    if category not in dict(UPDATE_FILTERS):
        category = "all"
    query = request.GET.get("q", "").strip()[:200]
    terms = query.casefold().split()
    results = [
        {"title": title, "anchor": anchor}
        for title, anchor, keywords in SEARCH_SECTIONS
        if terms and all(term in f"{title} {keywords}".casefold() for term in terms)
    ]
    content = list(Content.objects.public())
    faqs = list(FAQ.objects.filter(is_published=True))
    for item in content:
        if terms and all(term in f"{item.title} {item.summary} {item.body}".casefold() for term in terms):
            results.append({"title": item.title, "url": item.get_absolute_url()})
    for faq in faqs:
        if terms and all(term in f"{faq.question} {faq.answer}".casefold() for term in terms):
            results.append({"title": faq.question, "anchor": "faq"})
    managed_updates = [
        {"category": item.category, "label": item.get_category_display(), "title": item.title,
         "url": item.get_absolute_url(), "description": item.summary,
         "date_label": timezone.localtime(item.published_at).strftime("%d %B %Y")}
        for item in content if item.category != "project"
    ]
    return {
        "category": category,
        "filters": UPDATE_FILTERS,
        "updates": [item for item in managed_updates + list(UPDATES) if category == "all" or item["category"] == category],
        "projects": [item for item in content if item.category == "project"],
        "publications": [item for item in content if item.category == "publication"],
        "faqs": faqs,
        "subscription_form": SubscriptionForm(),
        "query": query,
        "search_results": results,
        "search_submitted": "q" in request.GET,
    }


@require_GET
def home(request):
    return render(request, "home.html", homepage_context(request))


@require_GET
@vary_on_headers("HX-Request")
def search(request):
    template = "partials/search-results.html" if request.headers.get("HX-Request") == "true" else "home.html"
    return render(request, template, homepage_context(request))


@require_GET
@vary_on_headers("HX-Request")
def updates(request):
    template = "partials/updates.html" if request.headers.get("HX-Request") == "true" else "home.html"
    return render(request, template, homepage_context(request))


@require_GET
def content_detail(request, slug):
    item = get_object_or_404(Content.objects.public(), slug=slug)
    return render(request, "content-detail.html", {"item": item})


@require_POST
def subscribe(request):
    form = SubscriptionForm(request.POST)
    if not form.is_valid():
        context = homepage_context(request)
        context["subscription_form"] = form
        return render(request, "home.html", context, status=400)
    mail_failed = False
    if not form.cleaned_data["website"]:
        now = timezone.now()
        with transaction.atomic():
            subscriber, created = Subscriber.objects.get_or_create(email=form.cleaned_data["email"])
            subscriber = Subscriber.objects.select_for_update().get(pk=subscriber.pk)
            if created or subscriber.requested_at < now - timedelta(minutes=5):
                subscriber.pending_topics = form.cleaned_data["topics"]
                subscriber.requested_at = now
                subscriber.save(update_fields=["pending_topics", "requested_at"])
                try:
                    count = send_mail("Confirm your ministry email updates",
                        "Confirm your subscription or topic changes using this link (valid for 48 hours):\n\n"
                        + subscription_url(subscriber, "confirm_subscription")
                        + "\n\nWe will only send updates after you confirm. If you did not request this, ignore this email.\n",
                        settings.DEFAULT_FROM_EMAIL, [subscriber.email])
                    if count != 1:
                        raise RuntimeError("Email backend did not accept the confirmation")
                except Exception:
                    logger.exception("Subscription confirmation could not be sent")
                    transaction.set_rollback(True)
                    mail_failed = True
    if mail_failed:
        context = homepage_context(request)
        context["subscription_form"] = form
        context["subscription_error"] = "We couldn’t send your confirmation email. Please try again later."
        return render(request, "home.html", context, status=503)
    messages.success(request, "Check your inbox for a confirmation link. If you recently requested one, please use that email. Your choices take effect after confirmation.")
    return redirect(reverse("home") + "#subscribe")


def token_subscriber(token, action):
    try:
        data = signing.loads(token, salt=f"subscription-{action}",
            max_age=60 * 60 * 48 if action == "confirm_subscription" else None)
        return Subscriber.objects.filter(pk=data["id"], token=data["token"]).first()
    except (signing.BadSignature, KeyError, ValueError, TypeError):
        return None


@require_http_methods(["GET", "POST"])
def confirm_subscription(request, token):
    subscriber = token_subscriber(token, "confirm_subscription")
    if subscriber is None:
        return render(request, "subscription-action.html", {"invalid": True}, status=400)
    if request.method == "POST":
        subscriber.topics = subscriber.pending_topics
        if not subscriber.is_active:
            subscriber.confirmed_at = timezone.now()
        subscriber.is_active = True
        subscriber.save(update_fields=["topics", "confirmed_at", "is_active"])
        return render(request, "subscription-action.html", {"confirmed": True})
    return render(request, "subscription-action.html", {"action": "confirm", "subscriber": subscriber})


@require_http_methods(["GET", "POST"])
def unsubscribe(request, token):
    subscriber = token_subscriber(token, "unsubscribe")
    if subscriber is None:
        return render(request, "subscription-action.html", {"invalid": True}, status=400)
    if request.method == "POST":
        subscriber.is_active = False
        subscriber.token = uuid.uuid4()
        subscriber.save(update_fields=["is_active", "token"])
        return render(request, "subscription-action.html", {"unsubscribed": True})
    return render(request, "subscription-action.html", {"action": "unsubscribe", "subscriber": subscriber})

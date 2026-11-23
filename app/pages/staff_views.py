from functools import wraps

from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .forms import ContentForm, FAQForm, StaffLoginForm
from .models import Content, FAQ, Subscriber


class StaffLoginView(LoginView):
    template_name = "staff/login.html"
    authentication_form = StaffLoginForm
    next_page = reverse_lazy("staff_dashboard")


class StaffLogoutView(LogoutView):
    next_page = reverse_lazy("staff_login")


def staff_permission(permission=None):
    def decorate(view):
        @never_cache
        @login_required(login_url="staff_login", redirect_field_name=REDIRECT_FIELD_NAME)
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_active or not user.is_staff:
                raise PermissionDenied
            if permission and not user.has_perm(permission):
                raise PermissionDenied
            if not permission and not any(user.has_perm(f"pages.view_{model}") for model in ("content", "faq", "subscriber")):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


@staff_permission()
@require_GET
def dashboard(request):
    context = {}
    if request.user.has_perm("pages.view_content"):
        context.update(content_count=Content.objects.count(),
            draft_count=Content.objects.filter(is_published=False).count(),
            published_count=Content.objects.public().count(),
            scheduled_count=Content.objects.filter(is_published=True, published_at__gt=timezone.now()).count(),
            recent_content=Content.objects.all()[:6])
    if request.user.has_perm("pages.view_faq"):
        context["faq_count"] = FAQ.objects.count()
    return render(request, "staff/dashboard.html", context)


@staff_permission("pages.view_content")
@require_GET
def content_list(request):
    items = Content.objects.all()
    query = request.GET.get("q", "").strip()[:200]
    category = request.GET.get("category", "")
    status = request.GET.get("status", "")
    if query:
        items = items.filter(Q(title__icontains=query) | Q(summary__icontains=query))
    if category in Content.Category.values:
        items = items.filter(category=category)
    if status == "draft":
        items = items.filter(is_published=False)
    elif status == "published":
        items = items.public()
    elif status == "scheduled":
        items = items.filter(is_published=True, published_at__gt=timezone.now())
    return render(request, "staff/content-list.html", {"page_obj": Paginator(items, 15).get_page(request.GET.get("page")),
        "query": query, "category": category, "status": status, "categories": Content.Category.choices})


@staff_permission("pages.add_content")
@require_http_methods(["GET", "POST"])
def content_create(request):
    initial = {}
    if request.GET.get("category") in Content.Category.values:
        initial["category"] = request.GET["category"]
    form = ContentForm(request.POST if request.method == "POST" else None, request.FILES or None, initial=initial)
    return save_content(request, form)


@staff_permission("pages.change_content")
@require_http_methods(["GET", "POST"])
def content_edit(request, pk):
    item = get_object_or_404(Content, pk=pk)
    form = ContentForm(request.POST if request.method == "POST" else None, request.FILES or None, instance=item)
    return save_content(request, form, item)


def save_content(request, form, item=None):
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f'“{saved.title}” saved.')
        return redirect("staff_content_list")
    return render(request, "staff/content-form.html", {"form": form, "item": item})


@staff_permission("pages.view_content")
@require_GET
def content_preview(request, pk):
    return render(request, "staff/content-preview.html", {"item": get_object_or_404(Content, pk=pk)})


@staff_permission("pages.delete_content")
@require_http_methods(["GET", "POST"])
def content_delete(request, pk):
    item = get_object_or_404(Content, pk=pk)
    if request.method == "POST":
        item.delete()
        messages.success(request, "Content deleted.")
        return redirect("staff_content_list")
    return render(request, "staff/delete.html", {"item": item, "cancel_url": "staff_content_list"})


@staff_permission("pages.view_faq")
@require_GET
def faq_list(request):
    return render(request, "staff/faq-list.html", {"page_obj": Paginator(FAQ.objects.all(), 20).get_page(request.GET.get("page"))})


@staff_permission("pages.add_faq")
@require_http_methods(["GET", "POST"])
def faq_create(request):
    return save_faq(request, FAQForm(request.POST if request.method == "POST" else None))


@staff_permission("pages.change_faq")
@require_http_methods(["GET", "POST"])
def faq_edit(request, pk):
    item = get_object_or_404(FAQ, pk=pk)
    return save_faq(request, FAQForm(request.POST if request.method == "POST" else None, instance=item), item)


def save_faq(request, form, item=None):
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "FAQ saved.")
        return redirect("staff_faq_list")
    return render(request, "staff/faq-form.html", {"form": form, "item": item})


@staff_permission("pages.delete_faq")
@require_http_methods(["GET", "POST"])
def faq_delete(request, pk):
    item = get_object_or_404(FAQ, pk=pk)
    if request.method == "POST":
        item.delete()
        messages.success(request, "FAQ deleted.")
        return redirect("staff_faq_list")
    return render(request, "staff/delete.html", {"item": item, "cancel_url": "staff_faq_list"})


@staff_permission("pages.view_subscriber")
@require_GET
def subscriber_list(request):
    subscribers = Subscriber.objects.order_by("-requested_at")
    query = request.GET.get("q", "").strip()[:200]
    if query:
        subscribers = subscribers.filter(email__icontains=query)
    return render(request, "staff/subscribers.html", {"page_obj": Paginator(subscribers, 20).get_page(request.GET.get("page")),
        "query": query, "active_count": Subscriber.objects.filter(is_active=True, confirmed_at__isnull=False).count()})

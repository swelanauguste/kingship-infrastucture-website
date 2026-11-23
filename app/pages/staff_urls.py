from django.urls import path
from . import staff_views as views

urlpatterns = [
    path("", views.dashboard, name="staff_dashboard"),
    path("login/", views.StaffLoginView.as_view(), name="staff_login"),
    path("logout/", views.StaffLogoutView.as_view(), name="staff_logout"),
    path("content/", views.content_list, name="staff_content_list"),
    path("content/new/", views.content_create, name="staff_content_create"),
    path("content/<int:pk>/edit/", views.content_edit, name="staff_content_edit"),
    path("content/<int:pk>/preview/", views.content_preview, name="staff_content_preview"),
    path("content/<int:pk>/delete/", views.content_delete, name="staff_content_delete"),
    path("faqs/", views.faq_list, name="staff_faq_list"),
    path("faqs/new/", views.faq_create, name="staff_faq_create"),
    path("faqs/<int:pk>/edit/", views.faq_edit, name="staff_faq_edit"),
    path("faqs/<int:pk>/delete/", views.faq_delete, name="staff_faq_delete"),
    path("subscribers/", views.subscriber_list, name="staff_subscribers"),
]

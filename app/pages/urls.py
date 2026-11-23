from django.urls import path

from . import views

urlpatterns = [
    path("healthz/", views.health, name="health"),
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("updates/", views.updates, name="updates"),
    path("content/<slug:slug>/", views.content_detail, name="content_detail"),
    path("subscribe/", views.subscribe, name="subscribe"),
    path("subscribe/confirm/<str:token>/", views.confirm_subscription, name="confirm_subscription"),
    path("subscribe/unsubscribe/<str:token>/", views.unsubscribe, name="unsubscribe"),
]

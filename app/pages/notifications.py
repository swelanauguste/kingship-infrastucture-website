from django.conf import settings
from django.core import signing
from django.urls import reverse


def subscription_url(subscriber, action):
    token = signing.dumps({"id": subscriber.pk, "token": str(subscriber.token)}, salt=f"subscription-{action}")
    return settings.SITE_URL.rstrip("/") + reverse(action, kwargs={"token": token})

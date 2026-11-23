from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from pages.models import Content, NotificationDelivery, Subscriber
from pages.notifications import subscription_url


class Command(BaseCommand):
    help = "Send published content to confirmed subscribers once per item. Schedule a single worker every five minutes."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count eligible emails without sending or changing records.")

    def handle(self, *args, **options):
        sent = 0
        failed = 0
        for item in Content.objects.public().filter(notify_subscribers=True):
            subscribers = Subscriber.objects.filter(is_active=True, confirmed_at__lte=item.published_at)
            for subscriber in subscribers.iterator():
                if item.category not in subscriber.topics:
                    continue
                if NotificationDelivery.objects.filter(content=item, subscriber=subscriber, sent_at__isnull=False).exists():
                    continue
                if options["dry_run"]:
                    sent += 1
                    continue
                try:
                    with transaction.atomic():
                        delivery, _ = NotificationDelivery.objects.get_or_create(content=item, subscriber=subscriber)
                        delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery.pk)
                        if delivery.sent_at:
                            continue
                        # Check consent again immediately before sending.
                        subscriber.refresh_from_db()
                        if not subscriber.is_active or item.category not in subscriber.topics:
                            continue
                        body = (f"{item.get_category_display()}: {item.title}\n\n{item.summary}\n\n"
                            f"Read more: {settings.SITE_URL.rstrip('/')}{item.get_absolute_url()}\n\n"
                            f"Unsubscribe: {subscription_url(subscriber, 'unsubscribe')}\n")
                        count = send_mail(f"Ministry update: {item.title}", body,
                            settings.DEFAULT_FROM_EMAIL, [subscriber.email])
                        if count != 1:
                            raise RuntimeError("Email backend did not accept the message")
                        delivery.sent_at = timezone.now()
                        delivery.save(update_fields=["sent_at"])
                        sent += 1
                except Exception:
                    failed += 1
                    self.stderr.write(f"Delivery failed for item {item.pk}, subscriber {subscriber.pk}; retry on the next run.")
        self.stdout.write(f"{'Eligible' if options['dry_run'] else 'Sent'}: {sent}; failed: {failed}.")
        if failed:
            raise CommandError("Some notifications could not be sent.")

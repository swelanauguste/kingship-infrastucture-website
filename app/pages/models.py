from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.urls import reverse
from django.utils import timezone
import uuid


def validate_document_size(value):
    if value.size > 10 * 1024 * 1024:
        raise ValidationError("Please upload a PDF smaller than 10 MB.")


class ContentQuerySet(models.QuerySet):
    def public(self):
        return self.filter(is_published=True, published_at__lte=timezone.now())


class Content(models.Model):
    class Category(models.TextChoices):
        PUBLICATION = "publication", "Publication"
        NEWS = "news", "News"
        NOTICE = "notice", "Notice"
        PROJECT = "project", "Project / programme"

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    summary = models.TextField(max_length=600, help_text="Short description shown on the homepage.")
    body = models.TextField(help_text="Full article or project details. Plain text; paragraphs are preserved.")
    external_url = models.URLField(blank=True, help_text="Optional link to the official source or project website.")
    document = models.FileField(upload_to="publications/%Y/%m/", blank=True,
        validators=[FileExtensionValidator(["pdf"]), validate_document_size],
        help_text="Optional public PDF, up to 10 MB. Uploaded documents are publicly accessible.")
    is_published = models.BooleanField(default=False, verbose_name="Publish")
    published_at = models.DateTimeField(default=timezone.now, help_text="A future date schedules publication.")
    notify_subscribers = models.BooleanField(default=False,
        help_text="Include this item in the next notification run after publication.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ContentQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-pk"]
        verbose_name = "content item"
        verbose_name_plural = "publications, news, notices & projects"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("content_detail", kwargs={"slug": self.slug})

    @property
    def publication_status(self):
        if not self.is_published:
            return "Draft"
        return "Scheduled" if self.published_at > timezone.now() else "Published"


class FAQ(models.Model):
    question = models.CharField(max_length=250)
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question


class Subscriber(models.Model):
    email = models.EmailField(unique=True)
    topics = models.JSONField(default=list)
    token = models.UUIDField(default=uuid.uuid4, editable=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    requested_at = models.DateTimeField(default=timezone.now)
    pending_topics = models.JSONField(default=list)

    def __str__(self):
        return self.email


class NotificationDelivery(models.Model):
    content = models.ForeignKey(Content, on_delete=models.CASCADE)
    subscriber = models.ForeignKey(Subscriber, on_delete=models.CASCADE)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["content", "subscriber"], name="unique_notification_delivery")]

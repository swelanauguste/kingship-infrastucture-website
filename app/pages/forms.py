from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.text import slugify

from .models import Content, FAQ


class StaffLoginForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise forms.ValidationError("This account does not have staff access.", code="not_staff")


class ContentForm(forms.ModelForm):
    slug = forms.SlugField(required=False, max_length=220, label="Page address",
        help_text="Leave blank to generate from the title. Changing an existing address breaks its previous link.")
    published_at = forms.DateTimeField(label="Publication date and time",
        widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
        help_text="Saint Lucia time. Choose a future date to schedule publication.")

    class Meta:
        model = Content
        fields = ["category", "title", "slug", "summary", "body", "external_url", "document",
                  "is_published", "published_at", "notify_subscribers"]
        labels = {"body": "Full content", "is_published": "Publish this item", "external_url": "Official source link"}
        widgets = {"summary": forms.Textarea(attrs={"rows": 3}), "body": forms.Textarea(attrs={"rows": 12})}

    def clean_slug(self):
        value = self.cleaned_data.get("slug")
        existing = Content.objects.exclude(pk=self.instance.pk)
        if value:
            if existing.filter(slug=value).exists():
                raise forms.ValidationError("This page address is already in use. Please choose another.")
            return value
        root = slugify(self.cleaned_data.get("title", ""))[:200] or "ministry-update"
        value = root
        suffix = 2
        while existing.filter(slug=value).exists():
            value = f"{root}-{suffix}"
            suffix += 1
        return value


class FAQForm(forms.ModelForm):
    class Meta:
        model = FAQ
        fields = ["question", "answer", "order", "is_published"]
        labels = {"order": "Display order", "is_published": "Show on the website"}
        help_texts = {"order": "Lower numbers appear first."}
        widgets = {"answer": forms.Textarea(attrs={"rows": 6})}


class SubscriptionForm(forms.Form):
    email = forms.EmailField(label="Email address", max_length=254,
        widget=forms.EmailInput(attrs={"placeholder": "you@example.com", "autocomplete": "email"}))
    topics = forms.MultipleChoiceField(label="Send me updates about", choices=Content.Category.choices,
        initial=[value for value, label in Content.Category.choices], widget=forms.CheckboxSelectMultiple)
    consent = forms.BooleanField(label="I agree to receive ministry updates by email. I can unsubscribe at any time.")
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

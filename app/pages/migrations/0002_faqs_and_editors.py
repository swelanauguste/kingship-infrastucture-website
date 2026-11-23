from django.db import migrations


def setup_content(apps, schema_editor):
    FAQ = apps.get_model("pages", "FAQ")
    for order, (question, answer) in enumerate([
        ("Where can I find publications and policy documents?",
         "Visit Publications to read documents published on this website. The Browse publications link also takes you to the ministry’s official publication directory."),
        ("How do I find news, public notices and project updates?",
         "Use News & notices to browse announcements and filter by News, Notices or Publications. Visit Projects & programmes for project information and links to official project websites."),
        ("How do I subscribe to ministry notifications?",
         "Enter your email address in the subscription form, choose your topics and give your consent. Open the confirmation email and confirm your subscription. You can change your topics through the same form or unsubscribe using the link in any update."),
        ("How can I contact the ministry or access a service?",
         "Use the services section to find official service links. The Contact us section at the bottom of the page links to the official contact directory for the ministry."),
    ]):
        FAQ.objects.create(question=question, answer=answer, order=order)
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    group, _ = Group.objects.get_or_create(name="Content editors")
    for model in ("content", "faq"):
        content_type, _ = ContentType.objects.get_or_create(app_label="pages", model=model)
        for action in ("add", "change", "delete", "view"):
            permission, _ = Permission.objects.get_or_create(content_type=content_type,
                codename=f"{action}_{model}", defaults={"name": f"Can {action} {model}"})
            group.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [("pages", "0001_initial"), ("auth", "0012_alter_user_first_name_max_length"),
                    ("contenttypes", "0002_remove_content_type_name")]
    operations = [migrations.RunPython(setup_content, migrations.RunPython.noop)]

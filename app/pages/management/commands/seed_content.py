from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from pages.models import Content, FAQ


SAMPLES = [
    ("road-maintenance-guide", "publication", "Road maintenance planning guide",
     "An introduction to planning routine road maintenance, from inspections to community updates.",
     "A maintenance plan starts with a clear record of road conditions. Teams can record surface damage, drainage issues and locations that need closer assessment.\n\nA useful plan identifies priorities, proposed activities and how residents will receive updates. Staff can replace this example with an approved ministry guide and attach its PDF.", "published"),
    ("public-project-information", "publication", "Understanding public project information",
     "A reader’s guide to project summaries, programme milestones and published documents.",
     "Project information is easier to follow when it explains the purpose of the work, the area involved and where to find further details.\n\nThis example shows how a publication can introduce a document before linking to an approved PDF or official source. It does not describe an approved policy or an active project.", "published"),
    ("community-project-updates", "news", "Making project updates easier to follow",
     "A sample newsroom story showing how to explain infrastructure work in clear, practical language.",
     "A helpful update explains what is happening, why it matters and what readers can do next. Short paragraphs and a clear summary make information easier to find.\n\nFor a real story, add verified project details, approved quotations and an official source before publishing. This example does not announce a ministry initiative.", "published"),
    ("publications-library", "news", "Exploring the ministry’s publications library",
     "See how a news article can introduce publications and direct readers to supporting resources.",
     "The publications section brings together documents and supporting explanations. Visitors can open individual pages, read a summary and follow document links.\n\nThis sample article is available for staff to edit in the workspace. Replace it with an approved newsroom story when preparing the website for public use.", "published"),
    ("roadwork-notice-example", "notice", "How a roadworks advisory will appear",
     "An example of a public notice layout for work locations, travel guidance and contact information.",
     "A real roadworks advisory should include the verified location, work dates, expected access arrangements and a contact for enquiries.\n\nNo road closure or traffic restriction is announced by this sample. Staff can use this page to practise preparing a notice before saving a draft for review.", "published"),
    ("consultation-notice-example", "notice", "How a public consultation notice will appear",
     "A sample notice for consultation details, participation information and supporting documents.",
     "An approved consultation notice can explain the purpose of the consultation, who may participate, the meeting arrangements and how to submit feedback.\n\nThis example does not invite submissions or announce a meeting. Replace it with verified arrangements and approved contact information before use.", "published"),
    ("community-roads-programme", "project", "Community roads improvement programme",
     "A sample project page showing how road improvements, scope and progress can be presented.",
     "Project purpose\nDescribe the community need and the intended outcome in plain language.\n\nScope of work\nList the approved locations and activities, such as surface repairs or drainage improvements.\n\nProgress and next steps\nAdd verified milestones and supporting documents as they become available. This example represents no approved works, budget or delivery commitment.", "published"),
    ("drainage-resilience-programme", "project", "Drainage and resilience programme",
     "A sample programme overview for explaining drainage maintenance and resilient infrastructure.",
     "Programme overview\nUse this space to explain the programme’s purpose and the communities it serves.\n\nPlanned activities\nDescribe approved assessments, maintenance or construction activities. Include only confirmed locations and dates.\n\nPublic information\nAdd official links and approved project documents. This sample is for website demonstration and does not announce a funded programme.", "published"),
    ("draft-project-brief", "project", "Project brief awaiting review",
     "An unpublished example for practising the staff drafting and preview workflow.",
     "This draft is visible only in the staff workspace.\n\nAdd the project background, scope, approved milestones and contact information. Use Preview saved page to review your work, then publish when the content is approved.", "draft"),
    ("scheduled-news-example", "news", "Scheduled newsroom update",
     "A scheduled example for trying the publication date and time controls.",
     "This sample is scheduled seven days after the seed command first creates it. It becomes visible automatically at its publication time.\n\nStaff can edit the date, save it as a draft or replace the text with an approved update.", "scheduled"),
]


class Command(BaseCommand):
    help = "Add clearly labelled demonstration content. Safe to rerun; existing items and staff edits are preserved."

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        created_count = 0
        for index, (slug, category, title, summary, body, status) in enumerate(SAMPLES):
            _, created = Content.objects.get_or_create(slug=f"sample-{slug}", defaults={
                "title": f"{title} (sample)", "category": category,
                "summary": summary,
                "body": "Sample content for website preview. This is not an official ministry announcement.\n\n" + body,
                "is_published": status != "draft",
                "published_at": now + timedelta(days=7) if status == "scheduled" else now - timedelta(days=index + 1),
                "notify_subscribers": False,
            })
            created_count += int(created)
        faq_count = 0
        for order, question, answer in [
            (4, "Can I read updates without subscribing?", "Yes. Publications, news, notices and project pages can be read on this website without an account or an email subscription. Subscribing is optional."),
            (5, "Can I choose which email updates I receive?", "Yes. Choose publications, news, notices or projects and programmes in the subscription form. You can choose more than one topic. Submit the form again and confirm the email to change your choices."),
        ]:
            _, created = FAQ.objects.get_or_create(question=question, defaults={"answer": answer, "order": order})
            faq_count += int(created)
        self.stdout.write(self.style.SUCCESS(
            f"Created {created_count} content items and {faq_count} FAQs. Existing content preserved. Sample notifications disabled."))

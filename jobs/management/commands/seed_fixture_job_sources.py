from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from jobs.models import Company, JobSource


class Command(BaseCommand):
    help = "Create local-only Greenhouse and Lever fixture source configurations."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Fixture source configurations require DEBUG=True.")
        configurations = (
            ("Greenhouse Fixture Company (Not Real)", "Greenhouse Local Fixture", "greenhouse"),
            ("Lever Fixture Company (Not Real)", "Lever Local Fixture", "lever"),
        )
        for company_name, source_name, source_type in configurations:
            company, _ = Company.objects.update_or_create(
                name=company_name,
                defaults={"description": "Synthetic local import fixture; not a real company or hiring claim."},
            )
            source, _ = JobSource.objects.update_or_create(
                name=source_name,
                defaults={
                    "company": company,
                    "source_type": source_type,
                    "base_url": "https://example.test/fixtures/",
                    "board_identifier": "local-fixture",
                    "enabled": True,
                    "robots_policy_status": JobSource.ReviewStatus.NOT_APPLICABLE,
                    "terms_review_status": JobSource.ReviewStatus.NOT_APPLICABLE,
                    "minimum_request_interval_seconds": 0,
                    "notes": "Local JSON fixture only. Never contacts example.test.",
                },
            )
            self.stdout.write(f"{source_name}: source_id={source.pk}")

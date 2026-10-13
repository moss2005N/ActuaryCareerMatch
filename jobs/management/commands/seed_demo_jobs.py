from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from jobs.demo_jobs import seed_demonstration_jobs


class Command(BaseCommand):
    help = "Seed clearly fictional public demonstration jobs for local use."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demonstration jobs can only be seeded when DEBUG=True.")
        seeded, created, updated = seed_demonstration_jobs()
        self.stdout.write(
            self.style.SUCCESS(
                f"Fictional demo jobs seeded: {len(seeded)} total, "
                f"{created} created, {updated} updated."
            )
        )

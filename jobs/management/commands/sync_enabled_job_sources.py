from django.core.management.base import BaseCommand

from jobs.models import JobSource
from jobs.services import sync_source


class Command(BaseCommand):
    help = "Synchronize all enabled, explicitly approved job sources sequentially."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--verbose", action="store_true", dest="command_verbose")

    def handle(self, *args, **options):
        for source in JobSource.objects.filter(enabled=True).select_related("company"):
            result = sync_source(source, dry_run=options["dry_run"], limit=options["limit"])
            self.stdout.write(
                f"source={source.pk} status={result.status} seen={result.jobs_seen} "
                f"created={result.jobs_created} updated={result.jobs_updated} skipped={result.jobs_skipped}"
            )
            if options["command_verbose"] and result.error_summary:
                self.stdout.write(result.error_summary)


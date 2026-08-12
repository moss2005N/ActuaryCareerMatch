import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from jobs.models import JobSource
from jobs.services import sync_source


class Command(BaseCommand):
    help = "Synchronize one explicitly approved job source."

    def add_arguments(self, parser):
        parser.add_argument("source_id", type=int)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--verbose", action="store_true", dest="command_verbose")
        parser.add_argument("--fixture", help="Local JSON fixture path; makes no network request.")

    def handle(self, *args, **options):
        try:
            source = JobSource.objects.select_related("company").get(pk=options["source_id"])
        except JobSource.DoesNotExist as exc:
            raise CommandError("Job source does not exist.") from exc
        fixture_data = None
        if options["fixture"]:
            path = Path(options["fixture"]).resolve()
            try:
                fixture_data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise CommandError("Fixture could not be read as JSON.") from exc
        result = sync_source(source, dry_run=options["dry_run"], limit=options["limit"], fixture_data=fixture_data)
        self.stdout.write(
            f"source={source.pk} status={result.status} seen={result.jobs_seen} "
            f"created={result.jobs_created} updated={result.jobs_updated} "
            f"skipped={result.jobs_skipped} deactivated={result.jobs_deactivated} errors={result.error_count}"
        )
        if options["command_verbose"] and result.error_summary:
            self.stdout.write(result.error_summary)


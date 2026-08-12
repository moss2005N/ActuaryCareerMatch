from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import ImportRun, JobPosting


def import_from_adapter(adapter, company, defaults):
    """Run one authorized adapter and persist conservative, traceable updates."""
    source = adapter.source
    run = ImportRun.objects.create(source=source)
    if not source.enabled:
        run.status = ImportRun.Status.SKIPPED
        run.finished_at = timezone.now()
        run.error_message = "Source is disabled; no external request was made."
        run.save(update_fields=("status", "finished_at", "error_message"))
        return run
    source.last_sync_at = timezone.now()
    source.save(update_fields=("last_sync_at",))
    try:
        for raw in adapter.fetch():
            run.records_seen += 1
            item = adapter.normalize(raw)
            lookup = {"source": source, "external_job_id": item.external_job_id}
            values = {
                **defaults,
                "company": company,
                "title": item.title,
                "description": item.description,
                "source_url": item.source_url,
                "application_url": item.application_url,
                "location": item.location,
                "posted_at": item.posted_at,
                "salary_min": item.salary_min,
                "salary_max": item.salary_max,
                "source_name": source.name,
            }
            with transaction.atomic():
                _, created = JobPosting.objects.update_or_create(defaults=values, **lookup)
            run.records_created += int(created)
            run.records_updated += int(not created)
        run.status = ImportRun.Status.SUCCESS
        source.last_success_at = timezone.now()
        source.last_error = ""
    except (ValueError, ValidationError, IntegrityError) as exc:
        run.status = ImportRun.Status.FAILED
        run.error_message = str(exc)[:2000]
        source.last_error = run.error_message
        raise
    finally:
        run.finished_at = timezone.now()
        run.save()
        source.save(update_fields=("last_success_at", "last_error"))
    return run

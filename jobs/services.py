import logging
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from profiles.models import ActuarialExam, Skill

from .http import HTTPClientError, SourceHTTPClient
from .models import ImportRun, JobPosting, JobSource
from .relevance import is_actuarial_relevant
from .requirements import extract_requirements
from .sources.base import ImportPayloadError
from .sources.registry import adapter_class_for

logger = logging.getLogger("jobs.imports")


@dataclass
class SyncResult:
    source_id: int
    status: str = ImportRun.Status.RUNNING
    jobs_seen: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    jobs_skipped: int = 0
    jobs_deactivated: int = 0
    error_count: int = 0
    error_summary: str = ""
    run_id: int | None = None

    @property
    def records_seen(self):
        return self.jobs_seen

    @property
    def records_created(self):
        return self.jobs_created

    @property
    def records_updated(self):
        return self.jobs_updated


def source_is_approved(source):
    allowed = {JobSource.ReviewStatus.ALLOWED, JobSource.ReviewStatus.NOT_APPLICABLE}
    return source.robots_policy_status in allowed and source.terms_review_status in allowed


def _job_values(item, source, company, existing=None):
    requirements = extract_requirements(item.raw_source_text or item.description)
    now = timezone.now()
    return {
        "company": company,
        "title": item.title,
        "description": item.description,
        "raw_source_text": item.raw_source_text or item.description,
        "source_url": item.source_url,
        "application_url": item.application_url,
        "location": item.location,
        "city": item.city,
        "state_or_region": item.state_or_region,
        "country": item.country,
        "employment_type": item.employment_type,
        "work_arrangement": item.work_arrangement or requirements.work_arrangement,
        "experience_level": item.experience_level,
        "posted_at": item.posted_at,
        "expires_at": item.expires_at,
        "salary_min": item.salary_min,
        "salary_max": item.salary_max,
        "salary_currency": item.salary_currency or "USD",
        "salary_period": item.salary_period,
        "source_name": source.name,
        "minimum_gpa": requirements.minimum_gpa,
        "degree_requirement": requirements.degree_requirement or JobPosting.DegreeRequirement.UNSPECIFIED,
        "sponsorship_available": requirements.sponsorship_available,
        "years_experience": requirements.years_experience,
        "first_seen_at": existing.first_seen_at if existing and existing.first_seen_at else now,
        "last_seen_at": now,
        "consecutive_missing_syncs": 0,
    }, requirements


def _persist_item(item, source, company):
    existing = JobPosting.objects.filter(source=source, external_job_id=item.external_job_id).first()
    values, requirements = _job_values(item, source, company, existing)
    if existing:
        for field, value in values.items():
            setattr(existing, field, value)
        existing.full_clean(exclude=("practice_areas", "required_exams", "preferred_exams", "required_skills", "preferred_skills"))
        existing.save()
        job, created = existing, False
    else:
        job = JobPosting(source=source, external_job_id=item.external_job_id, active=not item.explicitly_closed, **values)
        job.full_clean(exclude=("practice_areas", "required_exams", "preferred_exams", "required_skills", "preferred_skills"))
        job.save()
        created = True
    if item.explicitly_closed and job.active:
        job.active = False
        job.save(update_fields=("active",))
    exams = ActuarialExam.objects.filter(code__in=requirements.exam_codes, active=True)
    skills = Skill.objects.filter(name__in=requirements.skill_names, active=True)
    job.preferred_exams.set(exams)
    job.preferred_skills.set(skills)
    return job, created


def sync_source(source, *, dry_run=False, limit=None, fixture_data=None, adapter_class=None):
    result = SyncResult(source_id=source.pk)
    if not source.enabled and not dry_run:
        result.status = ImportRun.Status.SKIPPED
        result.error_summary = "Source is disabled; no request was made."
        return _finish(source, result, dry_run)
    if not source.company:
        result.status = ImportRun.Status.SKIPPED
        result.error_summary = "Source has no company configuration."
        return _finish(source, result, dry_run)
    if not source_is_approved(source):
        result.status = ImportRun.Status.SKIPPED
        result.error_summary = "Terms and robots policy review must be allowed before synchronization."
        return _finish(source, result, dry_run)
    adapter_class = adapter_class or adapter_class_for(source)
    if adapter_class is None:
        result.status = ImportRun.Status.SKIPPED
        result.error_summary = "No explicit adapter is configured for this source type."
        return _finish(source, result, dry_run)

    run = None if dry_run else ImportRun.objects.create(source=source)
    result.run_id = run.pk if run else None
    client = SourceHTTPClient(source)
    adapter = adapter_class(source, http_client=client, fixture_data=fixture_data)
    seen_ids = set()
    errors = []
    try:
        records = adapter.fetch(limit=limit)
        for raw in records:
            result.jobs_seen += 1
            try:
                item = adapter.normalize(raw)
                # Public-source imports deliberately require the actuarial signal in
                # the title. Descriptions often mention collaboration with an
                # actuarial team for otherwise unrelated insurance roles.
                if not is_actuarial_relevant(item.title):
                    result.jobs_skipped += 1
                    continue
                seen_ids.add(item.external_job_id)
                if dry_run:
                    continue
                with transaction.atomic():
                    _, created = _persist_item(item, source, source.company)
                result.jobs_created += int(created)
                result.jobs_updated += int(not created)
            except (ImportPayloadError, ValidationError, IntegrityError, ValueError) as exc:
                result.error_count += 1
                result.jobs_skipped += 1
                errors.append(f"{type(exc).__name__}: {str(exc)[:250]}")
        if not dry_run and not errors:
            unseen = JobPosting.objects.filter(source=source).exclude(external_job_id__in=seen_ids)
            for job in unseen:
                job.consecutive_missing_syncs += 1
                if job.active and job.consecutive_missing_syncs >= source.missing_syncs_before_deactivation:
                    job.active = False
                    result.jobs_deactivated += 1
                    job.save(update_fields=("consecutive_missing_syncs", "active"))
                else:
                    job.save(update_fields=("consecutive_missing_syncs",))
        result.status = ImportRun.Status.PARTIAL if result.error_count else ImportRun.Status.SUCCESS
    except (HTTPClientError, ImportPayloadError, ValidationError, ValueError) as exc:
        result.status = ImportRun.Status.FAILED
        result.error_count += 1
        errors.append(f"{type(exc).__name__}: {str(exc)[:500]}")
    result.error_summary = "\n".join(errors[:20])
    return _finish(source, result, dry_run, run)


def _finish(source, result, dry_run, run=None):
    if dry_run:
        return result
    now = timezone.now()
    run = run or ImportRun.objects.create(source=source)
    run.status = result.status
    run.finished_at = now
    for field in ("jobs_seen", "jobs_created", "jobs_updated", "jobs_skipped", "jobs_deactivated", "error_count", "error_summary"):
        setattr(run, field, getattr(result, field))
    run.save()
    source.last_sync_at = now
    if result.status in (ImportRun.Status.SUCCESS, ImportRun.Status.PARTIAL):
        source.last_success_at = now
    source.last_error = result.error_summary
    if result.status == ImportRun.Status.FAILED and any(
        marker in result.error_summary for marker in ("HTTP 401", "HTTP 403", "CAPTCHA", "access block")
    ):
        source.enabled = False
    source.save(update_fields=("last_sync_at", "last_success_at", "last_error", "enabled"))
    result.run_id = run.pk
    logger.info(
        "job_import_complete source_id=%s run_id=%s status=%s seen=%s created=%s updated=%s skipped=%s deactivated=%s errors=%s",
        source.pk, run.pk, result.status, result.jobs_seen, result.jobs_created,
        result.jobs_updated, result.jobs_skipped, result.jobs_deactivated, result.error_count,
    )
    return result


def import_from_adapter(adapter, company, defaults=None):
    """Backward-compatible wrapper for custom authorized adapters."""
    if not adapter.source.company_id:
        adapter.source.company = company
        adapter.source.save(update_fields=("company",))
    return sync_source(adapter.source, adapter_class=lambda source, **kwargs: adapter)

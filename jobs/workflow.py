from django.db import transaction
from django.utils import timezone

from .models import JobApplication


@transaction.atomic
def save_application(application, *, previous_status=None):
    if not application.external_application_url_snapshot:
        application.external_application_url_snapshot = application.job.application_url
    application.full_clean()
    application.save()
    return application


def mark_job_applied(user, job):
    application = JobApplication.objects.filter(user=user, job=job).first()
    previous = application.status if application else None
    if application is None:
        application = JobApplication(user=user, job=job)
    application.status = JobApplication.Status.APPLIED
    application.applied_at = application.applied_at or timezone.localdate()
    return save_application(application, previous_status=previous)

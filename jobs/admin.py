from django.contrib import admin
from django.utils import timezone

from .models import Company, ImportRun, JobPosting, JobSource


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "industry", "headquarters", "company_size", "active", "updated_at")
    search_fields = ("name", "headquarters", "description")
    list_filter = ("industry", "company_size", "active")


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "location", "employment_type", "work_arrangement", "experience_level", "active", "expires_at")
    search_fields = ("title", "company__name", "description", "location", "external_job_id")
    list_filter = ("active", "employment_type", "work_arrangement", "experience_level", "practice_areas", "source")
    autocomplete_fields = ("company", "source")
    filter_horizontal = ("practice_areas", "required_exams", "preferred_exams", "required_skills", "preferred_skills")
    readonly_fields = ("created_at", "updated_at")
    actions = ("deactivate_selected", "deactivate_expired")
    fieldsets = (
        ("Job", {"fields": ("company", "title", "description", "active")}),
        ("Location and type", {"fields": ("location", "country", "state_or_region", "city", "employment_type", "work_arrangement", "experience_level")}),
        ("Compensation", {"fields": ("salary_min", "salary_max", "salary_currency", "salary_period")}),
        ("Actuarial requirements", {"fields": ("practice_areas", "required_exams", "preferred_exams", "required_skills", "preferred_skills")}),
        ("Candidate requirements", {"fields": ("minimum_gpa", "degree_requirement", "major_requirements", "work_authorization_requirement", "sponsorship_available", "years_experience")}),
        ("Application and source", {"fields": ("application_url", "source", "source_name", "source_url", "external_job_id")}),
        ("Lifecycle", {"fields": ("posted_at", "expires_at", "created_at", "updated_at")}),
    )

    @admin.action(description="Deactivate selected jobs")
    def deactivate_selected(self, request, queryset):
        queryset.update(active=False)

    @admin.action(description="Deactivate all expired jobs")
    def deactivate_expired(self, request, queryset):
        JobPosting.objects.filter(active=True, expires_at__lte=timezone.now()).update(active=False)


@admin.register(JobSource)
class JobSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "source_type", "enabled", "last_sync_at", "last_success_at")
    search_fields = ("name", "base_url", "last_error")
    list_filter = ("source_type", "enabled")
    readonly_fields = ("last_sync_at", "last_success_at", "last_error", "created_at", "updated_at")


@admin.register(ImportRun)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = ("source", "status", "started_at", "finished_at", "records_seen", "records_created", "records_updated")
    search_fields = ("source__name", "error_message")
    list_filter = ("status", "source")
    readonly_fields = tuple(field.name for field in ImportRun._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


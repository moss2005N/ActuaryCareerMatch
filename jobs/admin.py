from django.contrib import admin
from django.utils import timezone

from .models import Company, ImportRun, JobMatch, JobMatchExplanation, JobPosting, JobSource
from .services import sync_source


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "industry", "headquarters", "company_size", "active", "updated_at")
    search_fields = ("name", "headquarters", "description")
    list_filter = ("industry", "company_size", "active")


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "source", "location", "employment_type", "work_arrangement", "active", "last_seen_at", "expires_at")
    search_fields = ("title", "company__name", "description", "location", "external_job_id")
    list_filter = ("active", "employment_type", "work_arrangement", "experience_level", "practice_areas", "source")
    autocomplete_fields = ("company", "source")
    filter_horizontal = ("practice_areas", "required_exams", "preferred_exams", "required_skills", "preferred_skills")
    readonly_fields = ("first_seen_at", "last_seen_at", "consecutive_missing_syncs", "created_at", "updated_at")
    actions = ("deactivate_selected", "deactivate_expired")
    fieldsets = (
        ("Job", {"fields": ("company", "title", "description", "active")}),
        ("Location and type", {"fields": ("location", "country", "state_or_region", "city", "employment_type", "work_arrangement", "experience_level")}),
        ("Compensation", {"fields": ("salary_min", "salary_max", "salary_currency", "salary_period")}),
        ("Actuarial requirements", {"fields": ("practice_areas", "required_exams", "preferred_exams", "required_skills", "preferred_skills")}),
        ("Candidate requirements", {"fields": ("minimum_gpa", "degree_requirement", "major_requirements", "work_authorization_requirement", "sponsorship_available", "years_experience")}),
        ("Application and source", {"fields": ("application_url", "source", "source_name", "source_url", "external_job_id")}),
        ("Lifecycle", {"fields": ("posted_at", "expires_at", "first_seen_at", "last_seen_at", "consecutive_missing_syncs", "created_at", "updated_at")}),
    )

    @admin.action(description="Deactivate selected jobs")
    def deactivate_selected(self, request, queryset):
        queryset.update(active=False)

    @admin.action(description="Deactivate all expired jobs")
    def deactivate_expired(self, request, queryset):
        JobPosting.objects.filter(active=True, expires_at__lte=timezone.now()).update(active=False)


@admin.register(JobSource)
class JobSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "source_type", "enabled", "robots_policy_status", "terms_review_status", "last_sync_at", "last_success_at", "last_error_summary", "imported_job_count")
    search_fields = ("name", "company__name", "base_url", "board_identifier", "last_error")
    list_filter = ("source_type", "enabled", "robots_policy_status", "terms_review_status")
    autocomplete_fields = ("company",)
    readonly_fields = ("last_sync_at", "last_success_at", "last_error", "created_at", "updated_at")
    actions = ("sync_selected_sources", "disable_selected_sources")

    @admin.display(description="Last error")
    def last_error_summary(self, obj):
        return obj.last_error or "—"

    @admin.display(description="Imported jobs")
    def imported_job_count(self, obj):
        return obj.jobs.count()

    @admin.action(description="Synchronize selected approved sources")
    def sync_selected_sources(self, request, queryset):
        for source in queryset.select_related("company"):
            sync_source(source)

    @admin.action(description="Disable selected sources")
    def disable_selected_sources(self, request, queryset):
        queryset.update(enabled=False)


@admin.register(ImportRun)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = ("source", "status", "started_at", "finished_at", "jobs_seen", "jobs_created", "jobs_updated", "jobs_skipped", "jobs_deactivated", "error_count")
    search_fields = ("source__name", "error_summary")
    list_filter = ("status", "source")
    readonly_fields = tuple(field.name for field in ImportRun._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ScoreRangeFilter(admin.SimpleListFilter):
    title = "score range"
    parameter_name = "score_range"

    def lookups(self, request, model_admin):
        return (("high", "80–100"), ("medium", "50–79"), ("low", "0–49"))

    def queryset(self, request, queryset):
        if self.value() == "high": return queryset.filter(score__gte=80)
        if self.value() == "medium": return queryset.filter(score__gte=50, score__lt=80)
        if self.value() == "low": return queryset.filter(score__lt=50)
        return queryset


@admin.register(JobMatch)
class JobMatchAdmin(admin.ModelAdmin):
    list_display = ("user", "job", "company", "score", "eligibility_status", "calculated_at")
    list_filter = (ScoreRangeFilter, "eligibility_status", "job__company")
    search_fields = ("user__username", "user__email", "job__title", "job__company__name")
    readonly_fields = tuple(field.name for field in JobMatch._meta.fields)
    list_select_related = ("user", "job", "job__company")

    @admin.display(description="Company", ordering="job__company__name")
    def company(self, obj):
        return obj.job.company

    def has_add_permission(self, request):
        return False


@admin.register(JobMatchExplanation)
class JobMatchExplanationAdmin(admin.ModelAdmin):
    list_display = ("match", "provider", "provider_model", "updated_at")
    list_filter = ("provider", "updated_at")
    search_fields = ("match__user__username", "match__job__title")
    readonly_fields = tuple(field.name for field in JobMatchExplanation._meta.fields)

    def has_add_permission(self, request):
        return False

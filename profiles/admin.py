from django.contrib import admin

from .models import CandidateProfile


@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "full_name",
        "university",
        "preferred_employment_type",
        "updated_at",
    )
    search_fields = ("user__username", "user__email", "full_name", "university")
    list_filter = ("preferred_employment_type", "preferred_work_arrangement")
    readonly_fields = ("created_at", "updated_at")


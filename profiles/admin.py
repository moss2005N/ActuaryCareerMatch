from django.contrib import admin

from .models import (
    ActuarialExam,
    CandidateProfile,
    Education,
    PracticeArea,
    ResumeAnalysis,
    ResumeSuggestion,
    Skill,
    UserExam,
    UserSkill,
    WorkExperience,
)


@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "university", "preferred_employment_type", "updated_at")
    search_fields = ("user__username", "user__email", "full_name", "university")
    list_filter = ("preferred_employment_type", "preferred_work_arrangement", "target_job_level")
    readonly_fields = ("created_at", "updated_at")
    filter_horizontal = ("preferred_practice_areas",)


@admin.register(ActuarialExam)
class ActuarialExamAdmin(admin.ModelAdmin):
    list_display = ("organization", "code", "name", "active", "display_order")
    search_fields = ("code", "name")
    list_filter = ("organization", "active")


@admin.register(UserExam)
class UserExamAdmin(admin.ModelAdmin):
    list_display = ("user", "exam", "status", "passed_date", "planned_exam_date")
    search_fields = ("user__username", "user__email", "exam__code", "exam__name")
    list_filter = ("status", "exam__organization")


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "active")
    search_fields = ("name",)
    list_filter = ("category", "active")


@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display = ("user", "skill", "proficiency_level", "years_experience")
    search_fields = ("user__username", "user__email", "skill__name")
    list_filter = ("proficiency_level", "skill__category")


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ("user", "institution", "degree", "major", "graduation_date", "current")
    search_fields = ("user__username", "user__email", "institution", "major")
    list_filter = ("current",)


@admin.register(WorkExperience)
class WorkExperienceAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "job_title", "start_date", "end_date", "currently_working")
    search_fields = ("user__username", "user__email", "company", "job_title")
    list_filter = ("employment_type", "currently_working")


@admin.register(PracticeArea)
class PracticeAreaAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "display_order")
    search_fields = ("name",)
    list_filter = ("active",)


@admin.register(ResumeAnalysis)
class ResumeAnalysisAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "provider", "provider_model", "created_at", "updated_at", "has_error")
    list_filter = ("status", "provider", "created_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = tuple(field.name for field in ResumeAnalysis._meta.fields)
    exclude = ("extracted_data", "suggestions", "feedback")

    @admin.display(boolean=True, description="Error")
    def has_error(self, obj):
        return bool(obj.error_message)

    def has_add_permission(self, request):
        return False


@admin.register(ResumeSuggestion)
class ResumeSuggestionAdmin(admin.ModelAdmin):
    list_display = ("analysis", "kind", "status", "confidence", "reviewed_at")
    list_filter = ("kind", "status", "confidence")
    readonly_fields = tuple(field.name for field in ResumeSuggestion._meta.fields)
    exclude = ("payload", "source_snippet")

    def has_add_permission(self, request):
        return False

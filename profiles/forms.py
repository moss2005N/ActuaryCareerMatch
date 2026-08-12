from django import forms

from .models import (
    ActuarialExam,
    CandidateProfile,
    Education,
    PracticeArea,
    Skill,
    UserExam,
    UserSkill,
    WorkExperience,
)


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            elif isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs["class"] = "form-check"
            else:
                field.widget.attrs["class"] = "form-control"


class CandidateProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CandidateProfile
        exclude = ("user", "resume", "resume_original_filename", "created_at", "updated_at")
        widgets = {
            "expected_graduation_date": forms.DateInput(attrs={"type": "date"}),
            "preferred_practice_areas": forms.CheckboxSelectMultiple,
            "preferred_locations": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        selected = self.instance.preferred_practice_areas.all() if self.instance.pk else PracticeArea.objects.none()
        self.fields["preferred_practice_areas"].queryset = (
            PracticeArea.objects.filter(active=True) | selected
        ).distinct()


class UserExamForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = UserExam
        fields = ("exam", "status", "passed_date", "planned_exam_date", "notes")
        widgets = {
            "passed_date": forms.DateInput(attrs={"type": "date"}),
            "planned_exam_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        selected = [self.instance.exam_id] if self.instance and self.instance.pk else []
        self.fields["exam"].queryset = ActuarialExam.objects.filter(active=True).exclude(
            user_exams__user=user
        ) | ActuarialExam.objects.filter(pk__in=selected)


class UserSkillForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = UserSkill
        fields = ("skill", "proficiency_level", "years_experience")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        selected = [self.instance.skill_id] if self.instance and self.instance.pk else []
        self.fields["skill"].queryset = Skill.objects.filter(active=True).exclude(
            user_skills__user=user
        ) | Skill.objects.filter(pk__in=selected)


class EducationForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Education
        exclude = ("user",)
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "graduation_date": forms.DateInput(attrs={"type": "date"}),
        }


class WorkExperienceForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = WorkExperience
        exclude = ("user",)
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class ResumeForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CandidateProfile
        fields = ("resume",)
        widgets = {"resume": forms.ClearableFileInput(attrs={"accept": "application/pdf,.pdf"})}

    def clean_resume(self):
        upload = self.cleaned_data["resume"]
        if getattr(upload, "content_type", None) != "application/pdf":
            raise forms.ValidationError("Resume files must use the PDF MIME type.")
        return upload

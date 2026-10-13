from django import forms
from django.db.models import Q
from django.utils import timezone

from profiles.models import PracticeArea

from .models import Company, JobApplication, JobPosting


class JobFilterForm(forms.Form):
    keyword = forms.CharField(required=False)
    company = forms.ModelChoiceField(queryset=Company.objects.none(), required=False)
    location = forms.CharField(required=False)
    employment_type = forms.ChoiceField(required=False, choices=())
    work_arrangement = forms.ChoiceField(required=False, choices=())
    experience_level = forms.ChoiceField(required=False, choices=())
    practice_area = forms.ModelChoiceField(queryset=PracticeArea.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].queryset = Company.objects.filter(active=True)
        self.fields["practice_area"].queryset = PracticeArea.objects.filter(active=True)
        self.fields["employment_type"].choices = [("", "All employment types"), *JobPosting.EmploymentType.choices]
        self.fields["work_arrangement"].choices = [("", "All work arrangements"), *JobPosting.WorkArrangement.choices]
        self.fields["experience_level"].choices = [("", "All experience levels"), *JobPosting.ExperienceLevel.choices]
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select" if isinstance(field.widget, forms.Select) else "form-control"


class JobApplicationForm(forms.ModelForm):
    class Meta:
        model = JobApplication
        fields = ("status", "applied_at", "follow_up_date", "notes")
        widgets = {
            "applied_at": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "follow_up_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "notes": forms.Textarea(attrs={"rows": 6, "maxlength": 5000, "class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_applied_at(self):
        value = self.cleaned_data.get("applied_at")
        if value and value > timezone.localdate():
            raise forms.ValidationError("Application date cannot be in the future.")
        return value


class MyJobsFilterForm(forms.Form):
    TRACKING_CHOICES = (("", "Saved or tracked"), ("saved", "Has saved record"), ("applied", "Has application tracking"))
    FOLLOW_UP_CHOICES = (("", "All follow-ups"), ("due", "Due or overdue"), ("upcoming", "Upcoming"))

    status = forms.ChoiceField(required=False, choices=(("", "All statuses"), *JobApplication.Status.choices))
    company = forms.ModelChoiceField(required=False, queryset=Company.objects.none())
    tracking = forms.ChoiceField(required=False, choices=TRACKING_CHOICES)
    follow_up = forms.ChoiceField(required=False, choices=FOLLOW_UP_CHOICES)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].queryset = Company.objects.filter(
            Q(jobs__saved_by__user=user) | Q(jobs__applications__user=user)
        ).distinct().order_by("name")
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select"

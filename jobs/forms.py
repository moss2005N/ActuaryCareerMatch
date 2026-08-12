from django import forms

from profiles.models import PracticeArea

from .models import Company, JobPosting


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


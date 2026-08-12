from django.db.models import Q
from django.views.generic import DetailView, ListView

from .forms import JobFilterForm
from .models import JobPosting


class JobListView(ListView):
    model = JobPosting
    template_name = "jobs/job_list.html"
    context_object_name = "jobs"
    paginate_by = 10

    def get_queryset(self):
        queryset = JobPosting.objects.visible().select_related("company", "source").prefetch_related("practice_areas")
        self.filter_form = JobFilterForm(self.request.GET)
        if not self.filter_form.is_valid():
            return queryset
        data = self.filter_form.cleaned_data
        if data["keyword"]:
            term = data["keyword"]
            queryset = queryset.filter(
                Q(title__icontains=term)
                | Q(description__icontains=term)
                | Q(company__name__icontains=term)
            )
        if data["company"]:
            queryset = queryset.filter(company=data["company"])
        if data["location"]:
            queryset = queryset.filter(
                Q(location__icontains=data["location"])
                | Q(city__icontains=data["location"])
                | Q(state_or_region__icontains=data["location"])
                | Q(country__icontains=data["location"])
            )
        for field in ("employment_type", "work_arrangement", "experience_level"):
            if data[field]:
                queryset = queryset.filter(**{field: data[field]})
        if data["practice_area"]:
            queryset = queryset.filter(practice_areas=data["practice_area"])
        return queryset.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        query = self.request.GET.copy()
        query.pop("page", None)
        context["querystring"] = query.urlencode()
        return context


class JobDetailView(DetailView):
    model = JobPosting
    template_name = "jobs/job_detail.html"
    context_object_name = "job"

    def get_queryset(self):
        return JobPosting.objects.visible().select_related("company", "source").prefetch_related(
            "practice_areas", "required_exams", "preferred_exams", "required_skills", "preferred_skills"
        )


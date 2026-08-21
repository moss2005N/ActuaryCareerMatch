from django.db.models import Q
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from .forms import JobFilterForm
from .models import JobPosting
from .matching import get_or_recalculate_match, matching_queryset, profile_fingerprint, profile_is_match_ready
from .explanations import generate_explanation, get_cached_explanation
from profiles.resume_analysis.base import ResumeAnalysisError


class JobListView(ListView):
    model = JobPosting
    template_name = "jobs/job_list.html"
    context_object_name = "jobs"
    paginate_by = 10

    def get_queryset(self):
        queryset = matching_queryset()
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
        context["profile_match_ready"] = False
        if self.request.user.is_authenticated:
            context["profile_match_ready"] = profile_is_match_ready(self.request.user)
            current_profile_hash = profile_fingerprint(self.request.user)
            for job in context["jobs"]:
                job.candidate_match = get_or_recalculate_match(self.request.user, job, profile_hash=current_profile_hash)
        return context


class JobDetailView(DetailView):
    model = JobPosting
    template_name = "jobs/job_detail.html"
    context_object_name = "job"

    def get_queryset(self):
        return matching_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context["candidate_match"] = get_or_recalculate_match(self.request.user, self.object)
            context["profile_match_ready"] = profile_is_match_ready(self.request.user)
            context["enhanced_explanation"] = get_cached_explanation(self.request.user, context["candidate_match"])
        return context


class RecommendedJobsView(LoginRequiredMixin, ListView):
    template_name = "jobs/recommended.html"
    context_object_name = "recommendations"
    login_url = "accounts:login"

    def get_queryset(self):
        jobs = matching_queryset().exclude(source__board_identifier="local-fixture").exclude(source__name="Development Seed Data")
        current_profile_hash = profile_fingerprint(self.request.user)
        matches = [get_or_recalculate_match(self.request.user, job, profile_hash=current_profile_hash) for job in jobs]
        return sorted(matches, key=lambda item: (-item.score, item.job.title.lower()))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["profile_match_ready"] = profile_is_match_ready(self.request.user)
        return context


@login_required
@require_POST
def refresh_match_explanation(request, pk):
    job = get_object_or_404(matching_queryset(), pk=pk)
    match = get_or_recalculate_match(request.user, job)
    try:
        generate_explanation(request.user, match, force=True)
        messages.success(request, "Enhanced match explanation generated.")
    except ResumeAnalysisError as exc:
        messages.warning(request, f"Enhanced explanation unavailable: {exc} Deterministic strengths and gaps remain available.")
    return redirect("jobs:detail", pk=pk)

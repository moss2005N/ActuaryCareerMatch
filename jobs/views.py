from django.db.models import Prefetch, Q
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from .forms import JobApplicationForm, JobFilterForm, MyJobsFilterForm
from .models import JobApplication, JobMatch, JobPosting, SavedJob
from .matching import get_or_recalculate_match, matching_queryset, profile_fingerprint, profile_is_match_ready
from .explanations import generate_explanation, get_cached_explanation
from profiles.resume_analysis.base import ResumeAnalysisError
from .workflow import mark_job_applied, save_application


def _attach_workflow(user, jobs):
    jobs = list(jobs)
    ids = [job.pk for job in jobs]
    saved = {item.job_id: item for item in SavedJob.objects.filter(user=user, job_id__in=ids)}
    applications = {item.job_id: item for item in JobApplication.objects.filter(user=user, job_id__in=ids)}
    for job in jobs:
        job.user_saved_job = saved.get(job.pk)
        job.is_saved_by_user = job.user_saved_job is not None
        job.user_application = applications.get(job.pk)
    return jobs


def _safe_post_redirect(request, default_url):
    candidate = request.POST.get("next", "")
    if candidate and url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return candidate
    return default_url


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
            context["jobs"] = _attach_workflow(self.request.user, context["jobs"])
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
            self.object.is_saved_by_user = SavedJob.objects.filter(user=self.request.user, job=self.object).exists()
            self.object.user_application = JobApplication.objects.filter(user=self.request.user, job=self.object).first()
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
        _attach_workflow(self.request.user, [match.job for match in matches])
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


@require_POST
def save_job(request, pk):
    job = get_object_or_404(JobPosting, pk=pk)
    target = _safe_post_redirect(request, reverse("jobs:detail", args=[job.pk]))
    if not request.user.is_authenticated:
        return redirect_to_login(target)
    SavedJob.objects.get_or_create(user=request.user, job=job)
    messages.success(request, "Job saved.")
    return redirect(target)


@require_POST
def unsave_job(request, pk):
    job = get_object_or_404(JobPosting, pk=pk)
    target = _safe_post_redirect(request, reverse("jobs:detail", args=[job.pk]))
    if not request.user.is_authenticated:
        return redirect_to_login(target)
    SavedJob.objects.filter(user=request.user, job=job).delete()
    messages.info(request, "Job removed from saved jobs. Application history was preserved.")
    return redirect(target)


@require_POST
def start_tracking(request, pk):
    job = get_object_or_404(JobPosting, pk=pk)
    if not request.user.is_authenticated:
        return redirect_to_login(_safe_post_redirect(request, reverse("jobs:detail", args=[job.pk])))
    application = JobApplication.objects.filter(user=request.user, job=job).first()
    if application is None:
        application = save_application(JobApplication(user=request.user, job=job))
    return redirect("jobs:application_edit", pk=application.pk)


@require_POST
def mark_as_applied(request, pk):
    job = get_object_or_404(JobPosting, pk=pk)
    target = _safe_post_redirect(request, reverse("jobs:detail", args=[job.pk]))
    if not request.user.is_authenticated:
        return redirect_to_login(target)
    mark_job_applied(request.user, job)
    messages.success(request, "Application marked as applied. This records your confirmation; the platform did not submit an application.")
    return redirect(target)


@login_required
def application_edit(request, pk):
    application = get_object_or_404(
        JobApplication.objects.select_related("job", "job__company").prefetch_related("status_history"),
        pk=pk,
        user=request.user,
    )
    previous_status = application.status
    form = JobApplicationForm(request.POST or None, instance=application)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        save_application(record, previous_status=previous_status)
        messages.success(request, "Application tracking updated.")
        return redirect("jobs:application_edit", pk=application.pk)
    return render(request, "jobs/application_form.html", {"form": form, "application": application})


class MyJobsView(LoginRequiredMixin, TemplateView):
    template_name = "jobs/my_jobs.html"
    login_url = "accounts:login"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = MyJobsFilterForm(self.request.GET, user=self.request.user)
        queryset = JobPosting.objects.filter(Q(saved_by__user=self.request.user) | Q(applications__user=self.request.user)).select_related("company", "source").distinct()
        if form.is_valid():
            data = form.cleaned_data
            if data["status"]: queryset = queryset.filter(applications__user=self.request.user, applications__status=data["status"])
            if data["company"]: queryset = queryset.filter(company=data["company"])
            if data["tracking"] == "saved": queryset = queryset.filter(saved_by__user=self.request.user)
            elif data["tracking"] == "applied": queryset = queryset.filter(applications__user=self.request.user)
            today = timezone.localdate()
            if data["follow_up"] == "due": queryset = queryset.filter(applications__user=self.request.user, applications__follow_up_date__lte=today)
            elif data["follow_up"] == "upcoming": queryset = queryset.filter(applications__user=self.request.user, applications__follow_up_date__gt=today)
        jobs = _attach_workflow(self.request.user, queryset.order_by("-applications__updated_at", "-saved_by__saved_at").distinct())
        matches = {item.job_id: item for item in JobMatch.objects.filter(user=self.request.user, job_id__in=[job.pk for job in jobs])}
        for job in jobs: job.saved_match = matches.get(job.pk)
        applications = JobApplication.objects.filter(user=self.request.user)
        context.update(
            filter_form=form,
            jobs=jobs,
            today=timezone.localdate(),
            metrics={
                "saved": SavedJob.objects.filter(user=self.request.user).count(),
                "preparing": applications.filter(status=JobApplication.Status.PREPARING).count(),
                "applied": applications.filter(status__in=(JobApplication.Status.APPLIED, JobApplication.Status.ONLINE_ASSESSMENT)).count(),
                "interviewing": applications.filter(status__in=(JobApplication.Status.INTERVIEW, JobApplication.Status.FINAL_INTERVIEW)).count(),
                "offers": applications.filter(status=JobApplication.Status.OFFER).count(),
            },
        )
        return context

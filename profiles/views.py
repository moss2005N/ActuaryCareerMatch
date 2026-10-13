from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    CandidateProfileForm,
    EducationForm,
    ResumeForm,
    UserExamForm,
    UserSkillForm,
    WorkExperienceForm,
)
from .models import CandidateProfile, Education, ResumeSuggestion, UserExam, UserSkill, WorkExperience
from .resume_analysis.base import ResumeAnalysisError
from .resume_analysis.service import analyze_user_resume, apply_suggestion, ignore_suggestion, resume_identifier
from .services import calculate_profile_completeness


@login_required
def profile_detail(request):
    user = request.user
    return render(request, "profiles/profile_detail.html", {
        "profile": user.candidate_profile,
        "completeness": calculate_profile_completeness(user),
        "education": user.education_history.all()[:3],
        "exams": user.exams.select_related("exam").all()[:6],
        "skills": user.skills.select_related("skill").all()[:8],
        "experience": user.work_experiences.all()[:3],
    })


@login_required
def profile_edit(request):
    profile = request.user.candidate_profile
    form = CandidateProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("profiles:detail")
    return render(request, "profiles/profile_form.html", {"form": form})


def _owned_form_view(request, *, model, form_class, template, redirect_name, instance=None):
    form = form_class(request.POST or None, instance=instance, user=request.user) if form_class in (UserExamForm, UserSkillForm) else form_class(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        record.user = request.user
        record.save()
        messages.success(request, "Your profile record was saved.")
        return redirect(redirect_name)
    return form


@login_required
def exams(request):
    form = _owned_form_view(request, model=UserExam, form_class=UserExamForm, template="", redirect_name="profiles:exams")
    if not isinstance(form, UserExamForm):
        return form
    return render(request, "profiles/exams.html", {"form": form, "records": request.user.exams.select_related("exam")})


@login_required
def exam_edit(request, pk):
    record = get_object_or_404(UserExam, pk=pk, user=request.user)
    form = _owned_form_view(request, model=UserExam, form_class=UserExamForm, template="", redirect_name="profiles:exams", instance=record)
    if not isinstance(form, UserExamForm):
        return form
    return render(request, "profiles/record_form.html", {"form": form, "title": "Edit actuarial exam"})


@login_required
def skills(request):
    form = _owned_form_view(request, model=UserSkill, form_class=UserSkillForm, template="", redirect_name="profiles:skills")
    if not isinstance(form, UserSkillForm):
        return form
    return render(request, "profiles/skills.html", {"form": form, "records": request.user.skills.select_related("skill")})


@login_required
def skill_edit(request, pk):
    record = get_object_or_404(UserSkill, pk=pk, user=request.user)
    form = _owned_form_view(request, model=UserSkill, form_class=UserSkillForm, template="", redirect_name="profiles:skills", instance=record)
    if not isinstance(form, UserSkillForm):
        return form
    return render(request, "profiles/record_form.html", {"form": form, "title": "Edit skill"})


@login_required
def education(request):
    form = _owned_form_view(request, model=Education, form_class=EducationForm, template="", redirect_name="profiles:education")
    if not isinstance(form, EducationForm):
        return form
    return render(request, "profiles/education.html", {"form": form, "records": request.user.education_history.all()})


@login_required
def education_edit(request, pk):
    record = get_object_or_404(Education, pk=pk, user=request.user)
    form = _owned_form_view(request, model=Education, form_class=EducationForm, template="", redirect_name="profiles:education", instance=record)
    if not isinstance(form, EducationForm):
        return form
    return render(request, "profiles/record_form.html", {"form": form, "title": "Edit education"})


@login_required
def experience(request):
    form = _owned_form_view(request, model=WorkExperience, form_class=WorkExperienceForm, template="", redirect_name="profiles:experience")
    if not isinstance(form, WorkExperienceForm):
        return form
    return render(request, "profiles/experience.html", {"form": form, "records": request.user.work_experiences.all()})


@login_required
def experience_edit(request, pk):
    record = get_object_or_404(WorkExperience, pk=pk, user=request.user)
    form = _owned_form_view(request, model=WorkExperience, form_class=WorkExperienceForm, template="", redirect_name="profiles:experience", instance=record)
    if not isinstance(form, WorkExperienceForm):
        return form
    return render(request, "profiles/record_form.html", {"form": form, "title": "Edit experience"})


@login_required
def resume(request):
    profile = request.user.candidate_profile
    old_name = profile.resume.name
    form = ResumeForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        uploaded = request.FILES["resume"]
        record = form.save(commit=False)
        record.resume_original_filename = uploaded.name
        record.save()
        if old_name and old_name != record.resume.name:
            record.resume.storage.delete(old_name)
        messages.success(request, "Resume uploaded securely.")
        return redirect("profiles:resume")
    analysis = None
    if profile.resume:
        current_identifier = resume_identifier(profile)
        analysis = request.user.resume_analyses.filter(resume_identifier=current_identifier).prefetch_related("review_items").first()
    return render(request, "profiles/resume.html", {"form": form, "profile": profile, "analysis": analysis})


@login_required
@require_POST
def resume_analyze(request):
    try:
        analysis = analyze_user_resume(request.user)
    except ResumeAnalysisError as exc:
        messages.warning(request, str(exc))
        return redirect("profiles:resume")
    if analysis.status == analysis.Status.COMPLETED:
        messages.success(request, "Resume analysis completed. Review suggestions before accepting changes.")
    else:
        messages.warning(request, analysis.error_message or "Resume analysis is unavailable.")
    return redirect("profiles:resume")


@login_required
@require_POST
def resume_suggestion_accept(request, pk):
    suggestion = get_object_or_404(ResumeSuggestion.objects.select_related("analysis"), pk=pk, analysis__user=request.user)
    try:
        apply_suggestion(request.user, suggestion)
        messages.success(request, "Suggestion accepted and applied to your profile.")
    except ResumeAnalysisError as exc:
        messages.warning(request, str(exc))
    return redirect("profiles:resume")


@login_required
@require_POST
def resume_suggestion_ignore(request, pk):
    suggestion = get_object_or_404(ResumeSuggestion.objects.select_related("analysis"), pk=pk, analysis__user=request.user)
    try:
        ignore_suggestion(request.user, suggestion)
        messages.info(request, "Suggestion ignored. No profile data was changed.")
    except ResumeAnalysisError as exc:
        messages.warning(request, str(exc))
    return redirect("profiles:resume")


@login_required
def resume_download(request):
    profile = request.user.candidate_profile
    if not profile.resume:
        return redirect("profiles:resume")
    return FileResponse(profile.resume.open("rb"), as_attachment=True, filename=profile.resume_filename)


@login_required
@require_POST
def resume_delete(request):
    with transaction.atomic():
        profile = CandidateProfile.objects.select_for_update().get(user=request.user)
        name = profile.resume.name if profile.resume else ""
        storage = profile.resume.storage
        request.user.resume_analyses.all().delete()
        profile.resume = ""
        profile.resume_original_filename = ""
        profile.save(update_fields=["resume", "resume_original_filename"])
        if name:
            storage.delete(name)
    messages.success(request, "Resume and stored resume analysis data deleted.")
    return redirect("profiles:resume")


@login_required
@require_POST
def record_delete(request, kind, pk):
    models = {
        "exam": (UserExam, "profiles:exams"),
        "skill": (UserSkill, "profiles:skills"),
        "education": (Education, "profiles:education"),
        "experience": (WorkExperience, "profiles:experience"),
    }
    model, redirect_name = models.get(kind, (None, None))
    if model is None:
        return redirect("profiles:detail")
    get_object_or_404(model, pk=pk, user=request.user).delete()
    return redirect(redirect_name)

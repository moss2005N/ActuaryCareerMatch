import hashlib
import json
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from profiles.models import ActuarialExam, Education, ResumeAnalysis, ResumeSuggestion, Skill, UserExam, UserSkill, WorkExperience

from .base import ResumeAnalysisError
from .pdf import extract_pdf_text
from .providers import get_provider
from .validation import validate_analysis_output


def resume_identifier(profile):
    digest = hashlib.sha256()
    with profile.resume.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(kind, payload):
    return hashlib.sha256(f"{kind}:".encode() + json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _suggestions_for(user, data):
    items = []
    profile = user.candidate_profile
    for contact in data["contact"]:
        if contact.get("name") == "full_name" and contact.get("value") and not profile.full_name:
            payload = {"field": "full_name", "value": contact["value"]}
            items.append(("profile", f"Set full name to {contact['value']}", payload, contact))
    for education in data["education"]:
        if education.get("gpa") and profile.gpa != Decimal(education["gpa"]):
            payload = {"field": "gpa", "value": education["gpa"]}
            items.append(("profile", f"Update GPA to {education['gpa']}", payload, education))
        if education.get("institution") and not user.education_history.filter(institution__iexact=education["institution"], degree__iexact=education.get("degree", ""), major__iexact=education.get("major", "")).exists():
            payload = {key: education.get(key) for key in ("institution", "degree", "major", "gpa", "graduation_date")}
            items.append(("education", f"Add education: {education['institution']}", payload, education))
    for exam in data["exams"]:
        reference = ActuarialExam.objects.filter(code__iexact=exam["name"], active=True).first()
        if reference and not user.exams.filter(exam=reference).exists():
            payload = {"exam_id": reference.pk, "status": exam.get("status", "planned")}
            items.append(("exam", f"Add Exam {reference.code} — {payload['status'].title()}", payload, exam))
    for skill in data["skills"]:
        reference = Skill.objects.filter(name__iexact=skill["name"], active=True).first()
        if reference and not user.skills.filter(skill=reference).exists():
            payload = {"skill_id": reference.pk, "proficiency_level": "intermediate", "years_experience": "0.0"}
            items.append(("skill", f"Add skill: {reference.name} (review proficiency)", payload, skill))
    for experience in data["experience"]:
        if experience.get("company") and experience.get("job_title") and experience.get("start_date") and not user.work_experiences.filter(company__iexact=experience["company"], job_title__iexact=experience["job_title"], start_date=experience["start_date"]).exists():
            payload = {key: experience.get(key) for key in ("company", "job_title", "start_date", "end_date", "current", "description")}
            items.append(("experience", f"Add experience: {experience['job_title']} at {experience['company']}", payload, experience))
    return items


@transaction.atomic
def analyze_user_resume(user, provider=None):
    profile = user.candidate_profile
    if not profile.resume:
        raise ResumeAnalysisError("Upload a PDF resume before requesting analysis.")
    provider = provider or get_provider()
    identifier = resume_identifier(profile)
    analysis = ResumeAnalysis.objects.create(user=user, resume_identifier=identifier, provider=provider.name, provider_model=getattr(provider, "model", ""), status=ResumeAnalysis.Status.PENDING)
    try:
        with profile.resume.open("rb") as stream:
            text = extract_pdf_text(stream, max_pages=settings.RESUME_ANALYSIS_MAX_PAGES, max_characters=settings.RESUME_ANALYSIS_MAX_CHARACTERS)
        data = validate_analysis_output(provider.analyze_resume(text))
        summaries = []
        for kind, label, payload, source in _suggestions_for(user, data):
            fingerprint = _fingerprint(kind, payload)
            suggestion, _ = ResumeSuggestion.objects.get_or_create(analysis=analysis, fingerprint=fingerprint, defaults={"kind": kind, "label": label, "payload": payload, "confidence": source.get("confidence", "low"), "source_snippet": source.get("source_snippet", "")[:500]})
            summaries.append({"id": suggestion.pk, "kind": kind, "label": label})
        analysis.extracted_data = data
        analysis.suggestions = summaries
        analysis.feedback = data["feedback"]
        analysis.status = ResumeAnalysis.Status.COMPLETED
        analysis.save(update_fields=("extracted_data", "suggestions", "feedback", "status", "updated_at"))
    except Exception as exc:
        analysis.status = ResumeAnalysis.Status.FAILED
        analysis.error_message = str(exc)[:500] if isinstance(exc, ResumeAnalysisError) else "Resume analysis failed safely."
        analysis.save(update_fields=("status", "error_message", "updated_at"))
    return analysis


@transaction.atomic
def apply_suggestion(user, suggestion):
    if suggestion.analysis.user_id != user.pk or suggestion.status != ResumeSuggestion.Status.PENDING:
        raise ResumeAnalysisError("This suggestion cannot be applied.")
    payload = suggestion.payload
    if suggestion.kind == ResumeSuggestion.Kind.PROFILE:
        if payload.get("field") == "gpa": user.candidate_profile.gpa = Decimal(payload["value"])
        elif payload.get("field") == "full_name": user.candidate_profile.full_name = str(payload["value"])[:150]
        else: raise ResumeAnalysisError("Unsupported profile suggestion.")
        user.candidate_profile.full_clean(); user.candidate_profile.save()
    elif suggestion.kind == ResumeSuggestion.Kind.EXAM:
        exam = ActuarialExam.objects.get(pk=payload["exam_id"], active=True)
        UserExam.objects.get_or_create(user=user, exam=exam, defaults={"status": payload["status"]})
    elif suggestion.kind == ResumeSuggestion.Kind.SKILL:
        skill = Skill.objects.get(pk=payload["skill_id"], active=True)
        UserSkill.objects.get_or_create(user=user, skill=skill, defaults={"proficiency_level": payload["proficiency_level"], "years_experience": Decimal(payload["years_experience"])})
    elif suggestion.kind == ResumeSuggestion.Kind.EDUCATION:
        lookup = {"user": user, "institution": payload["institution"], "degree": payload.get("degree", ""), "major": payload.get("major", "")}
        if not Education.objects.filter(**lookup).exists():
            record = Education(**lookup, gpa=Decimal(payload["gpa"]) if payload.get("gpa") else None, graduation_date=payload.get("graduation_date") or None)
            record.full_clean(); record.save()
    elif suggestion.kind == ResumeSuggestion.Kind.EXPERIENCE:
        lookup = {"user": user, "company": payload["company"], "job_title": payload["job_title"], "start_date": payload["start_date"]}
        if not WorkExperience.objects.filter(**lookup).exists():
            record = WorkExperience(**lookup, end_date=payload.get("end_date") or None, currently_working=bool(payload.get("current")), description=payload.get("description") or "")
            record.full_clean(); record.save()
    suggestion.status = ResumeSuggestion.Status.ACCEPTED; suggestion.reviewed_at = timezone.now(); suggestion.save(update_fields=("status", "reviewed_at"))
    return suggestion


def ignore_suggestion(user, suggestion):
    if suggestion.analysis.user_id != user.pk or suggestion.status != ResumeSuggestion.Status.PENDING:
        raise ResumeAnalysisError("This suggestion cannot be ignored.")
    suggestion.status = ResumeSuggestion.Status.IGNORED; suggestion.reviewed_at = timezone.now(); suggestion.save(update_fields=("status", "reviewed_at"))
    return suggestion

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from profiles.models import CandidateProfile, Education, UserExam, UserSkill, WorkExperience

from .models import JobMatch, JobPosting


MATCH_WEIGHTS = {
    "exams": 20,
    "skills": 20,
    "experience": 15,
    "practice_area": 15,
    "employment_level": 10,
    "location": 8,
    "work_arrangement": 5,
    "gpa": 5,
    "degree_major": 2,
}

EXAM_STATUS_CREDIT = {
    UserExam.Status.PASSED: 1.0,
    UserExam.Status.REGISTERED: 0.65,
    UserExam.Status.STUDYING: 0.55,
    UserExam.Status.PLANNED: 0.25,
}
PROFICIENCY_CREDIT = {
    UserSkill.Proficiency.BEGINNER: 0.40,
    UserSkill.Proficiency.INTERMEDIATE: 0.65,
    UserSkill.Proficiency.ADVANCED: 0.85,
    UserSkill.Proficiency.EXPERT: 1.0,
}
DEGREE_RANK = {"high_school": 0, "associate": 1, "bachelor": 2, "master": 3, "doctorate": 4}
JOB_DEGREE_RANK = {"bachelor": 2, "master": 3, "doctorate": 4}


@dataclass(frozen=True)
class MatchResult:
    overall_score: int | None
    eligibility_status: str
    matched_items: list[str]
    missing_items: list[str]
    warnings: list[str]
    component_scores: dict[str, int | None]
    explanation: dict
    profile_complete: bool

    def as_json(self):
        return asdict(self)


def matching_queryset():
    return JobPosting.objects.visible().select_related("company", "source").prefetch_related(
        "practice_areas", "required_exams", "preferred_exams", "required_skills", "preferred_skills"
    )


def profile_is_match_ready(user):
    profile = user.candidate_profile
    basic = bool(profile.full_name and (profile.city or profile.state_or_region or profile.country))
    education = bool(
        (profile.degree_level and profile.major)
        or user.education_history.exists()
    )
    preferences = bool(
        profile.preferred_employment_type
        and profile.preferred_work_arrangement
        and profile.target_job_level
    )
    return basic and education and preferences and user.exams.exists() and user.skills.exists()


def calculate_experience_years(experiences, today=None):
    today = today or timezone.localdate()
    intervals = []
    for item in experiences:
        end = today if item.currently_working or not item.end_date else min(item.end_date, today)
        if item.start_date and item.start_date <= end:
            intervals.append((item.start_date, end))
    if not intervals:
        return Decimal("0.0")
    intervals.sort()
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    days = sum((end - start).days + 1 for start, end in merged)
    return (Decimal(days) / Decimal("365.25")).quantize(Decimal("0.1"))


def _component(score, details, applicable=True):
    return {"score": round(score) if applicable else None, "applicable": applicable, "details": details}


def _gpa(profile, job, matched, missing, warnings):
    if job.minimum_gpa is None:
        return _component(0, ["Job does not specify a minimum GPA."], False)
    if profile.gpa is None:
        warnings.append("Candidate GPA is missing; the stated GPA requirement cannot be confirmed.")
        return _component(0, ["Candidate GPA is not recorded."])
    gap = Decimal(job.minimum_gpa) - Decimal(profile.gpa)
    if gap <= 0:
        matched.append(f"GPA {profile.gpa} meets the {job.minimum_gpa} requirement.")
        return _component(100, ["Minimum GPA met."])
    if gap <= Decimal("0.25"):
        warnings.append(f"GPA is slightly below the stated minimum ({profile.gpa} vs {job.minimum_gpa}).")
        return _component(60, ["Candidate GPA is within 0.25 of the stated minimum."])
    missing.append(f"GPA {profile.gpa} is below the stated minimum of {job.minimum_gpa}.")
    return _component(15, ["Candidate GPA is more than 0.25 below the stated minimum."])


def _exams(user, job, matched, missing, warnings):
    required = list(job.required_exams.all())
    preferred = list(job.preferred_exams.all())
    if not required and not preferred:
        return _component(0, ["Job does not specify exam requirements or preferences."], False)
    records = {item.exam_id: item for item in user.exams.select_related("exam").all()}
    credits, details = [], []
    for exam in required:
        record = records.get(exam.pk)
        if record and record.status == UserExam.Status.PASSED:
            credits.append(1.0); matched.append(f"Required Exam {exam.code} passed.")
        else:
            credits.append(0.0); missing.append(f"Required Exam {exam.code} has not been passed.")
            warnings.append(f"Exam {exam.code} is a hard requirement and must be passed.")
        details.append({"exam": exam.code, "kind": "required", "status": record.status if record else "missing"})
    for exam in preferred:
        record = records.get(exam.pk)
        credit = EXAM_STATUS_CREDIT.get(record.status, 0.0) if record else 0.0
        credits.append(credit)
        if credit == 1:
            matched.append(f"Preferred Exam {exam.code} passed.")
        elif credit:
            matched.append(f"Preferred Exam {exam.code} is {record.get_status_display().lower()}.")
        else:
            missing.append(f"Preferred Exam {exam.code} is not recorded.")
        details.append({"exam": exam.code, "kind": "preferred", "status": record.status if record else "missing"})
    return _component(100 * sum(credits) / len(credits), details)


def _skills(user, job, matched, missing, warnings):
    required = list(job.required_skills.all())
    preferred = list(job.preferred_skills.all())
    if not required and not preferred:
        return _component(0, ["Job does not specify structured skills."], False)
    records = {item.skill_id: item for item in user.skills.select_related("skill").all()}
    credits, details = [], []
    for skill, kind in [(s, "required") for s in required] + [(s, "preferred") for s in preferred]:
        record = records.get(skill.pk)
        credit = PROFICIENCY_CREDIT.get(record.proficiency_level, 0.0) if record else 0.0
        credits.append(credit)
        if record:
            matched.append(f"{skill.name} matched at {record.get_proficiency_level_display().lower()} proficiency.")
        else:
            missing.append(f"{kind.title()} skill {skill.name} is not recorded.")
            if kind == "required":
                warnings.append(f"Required skill {skill.name} is missing.")
        details.append({"skill": skill.name, "kind": kind, "proficiency": record.proficiency_level if record else "missing", "years": str(record.years_experience) if record else None})
    return _component(100 * sum(credits) / len(credits), details)


def _experience(user, job, matched, missing, warnings, today=None):
    if job.years_experience is None:
        return _component(0, ["Job does not specify minimum experience."], False)
    candidate = calculate_experience_years(user.work_experiences.all(), today=today)
    required = Decimal(job.years_experience)
    if required == 0 or candidate >= required:
        matched.append(f"Experience requirement met ({candidate} years recorded).")
        score = 100
    else:
        ratio = float(candidate / required) if required else 1
        score = max(10, round(100 * ratio))
        missing.append(f"Job requests {required} years; candidate has {candidate} non-overlapping years recorded.")
        warnings.append("Recorded professional experience is below the stated minimum.")
    return _component(score, [{"candidate_years": str(candidate), "required_years": str(required)}])


def _practice(profile, job, matched, missing):
    job_ids = {area.pk for area in job.practice_areas.all()}
    if not job_ids:
        return _component(0, ["Job has no structured practice area."], False)
    preferred = {area.pk: area.name for area in profile.preferred_practice_areas.all()}
    if not preferred:
        return _component(50, ["Candidate has no practice-area preference."])
    common = job_ids & preferred.keys()
    if common:
        names = ", ".join(preferred[pk] for pk in common)
        matched.append(f"Preferred practice area matched: {names}.")
        return _component(100, ["At least one preferred practice area matches."])
    missing.append("Job practice area differs from the candidate's stated preferences.")
    return _component(20, ["Structured practice areas do not overlap."])


def _employment_level(profile, job, matched, warnings):
    scores, details = [], []
    if job.employment_type:
        score = 100 if profile.preferred_employment_type == job.employment_type else 25
        scores.append(score); details.append("employment_type")
        if score == 100: matched.append("Preferred employment type matches.")
    level_map = {
        "internship": {"internship": 100, "entry": 45, "experienced": 5},
        "entry": {"internship": 55, "entry": 100, "experienced": 20},
        "associate": {"internship": 20, "entry": 80, "experienced": 60},
        "mid": {"internship": 5, "entry": 45, "experienced": 90},
        "senior": {"internship": 0, "entry": 20, "experienced": 100},
    }
    if job.experience_level:
        score = level_map.get(profile.target_job_level, {}).get(job.experience_level, 40)
        scores.append(score); details.append("target_level")
        if score >= 80: matched.append("Target job level aligns.")
        elif score <= 25: warnings.append("Target level and job experience level differ substantially.")
    return _component(sum(scores) / len(scores) if scores else 0, details or ["Job does not specify employment type or experience level."], bool(scores))


def _location(profile, job, matched):
    if job.work_arrangement == JobPosting.WorkArrangement.REMOTE or "remote" in job.location.lower():
        if profile.preferred_work_arrangement in (CandidateProfile.WorkArrangement.REMOTE, CandidateProfile.WorkArrangement.FLEXIBLE):
            matched.append("Remote location matches the candidate's preference.")
            return _component(100, ["Remote accepted."])
        return _component(45, ["Job is remote but remote work is not the stated preference."])
    location = " ".join(filter(None, (job.city, job.state_or_region, job.country, job.location))).lower()
    if not location:
        return _component(0, ["Job location is not specified."], False)
    preferred = [x.strip().lower() for x in profile.preferred_locations.splitlines() if x.strip()]
    current = " ".join(filter(None, (profile.city, profile.state_or_region, profile.country))).lower()
    if any(item in location or location in item for item in preferred) or (current and any(part and part in location for part in (profile.city.lower(), profile.state_or_region.lower(), profile.country.lower()))):
        matched.append("Job location matches a current or preferred location.")
        return _component(100, ["Location text matched conservatively."])
    if profile.willing_to_relocate:
        matched.append("Candidate is willing to relocate.")
        return _component(75, ["No location match, but relocation is accepted."])
    return _component(20, ["No current/preferred location match and relocation is not selected."])


def _arrangement(profile, job, matched):
    if not job.work_arrangement:
        return _component(0, ["Job does not specify work arrangement."], False)
    if profile.preferred_work_arrangement == CandidateProfile.WorkArrangement.FLEXIBLE or profile.preferred_work_arrangement == job.work_arrangement:
        matched.append("Preferred work arrangement matches.")
        return _component(100, ["Work arrangement aligned."])
    return _component(25, ["Work arrangement differs from stated preference."])


def _candidate_degree(profile, education):
    if profile.degree_level in DEGREE_RANK:
        return profile.degree_level
    text = " ".join(item.degree.lower() for item in education)
    for level, terms in (("doctorate", ("phd", "ph.d", "doctor")), ("master", ("master", "ms", "m.s")), ("bachelor", ("bachelor", "bs", "ba", "b.s", "b.a")), ("associate", ("associate",))):
        if any(term in text for term in terms): return level
    return ""


def _degree_major(user, profile, job, matched, missing, warnings):
    requirements = [line.strip().lower() for line in job.major_requirements.splitlines() if line.strip()]
    degree_required = job.degree_requirement in JOB_DEGREE_RANK
    if not degree_required and not requirements:
        return _component(0, ["Job does not specify degree or major requirements."], False)
    education = list(user.education_history.all())
    scores = []
    if degree_required:
        candidate = _candidate_degree(profile, education)
        if not candidate:
            scores.append(0); warnings.append("Candidate degree level is missing.")
        elif DEGREE_RANK.get(candidate, -1) >= JOB_DEGREE_RANK[job.degree_requirement]:
            scores.append(100); matched.append(f"{job.get_degree_requirement_display()} requirement met.")
        else:
            scores.append(0); missing.append(f"Job requires {job.get_degree_requirement_display()}; recorded degree level is lower.")
    if requirements:
        candidate_majors = [profile.major.lower(), *(item.major.lower() for item in education)]
        if any(req in major or major in req for req in requirements for major in candidate_majors if major):
            scores.append(100); matched.append("Major requirement matched.")
        else:
            scores.append(0); missing.append("Recorded major does not match the explicit major requirement.")
    return _component(sum(scores) / len(scores), requirements)


def calculate_match(user, job, today=None):
    matched, missing, warnings = [], [], []
    profile = user.candidate_profile
    components = {
        "gpa": _gpa(profile, job, matched, missing, warnings),
        "exams": _exams(user, job, matched, missing, warnings),
        "skills": _skills(user, job, matched, missing, warnings),
        "experience": _experience(user, job, matched, missing, warnings, today=today),
        "practice_area": _practice(profile, job, matched, missing),
        "employment_level": _employment_level(profile, job, matched, warnings),
        "location": _location(profile, job, matched),
        "work_arrangement": _arrangement(profile, job, matched),
        "degree_major": _degree_major(user, profile, job, matched, missing, warnings),
    }
    hard_failures, hard_unknowns = [], []
    required_passed = {x.exam_id for x in user.exams.filter(status=UserExam.Status.PASSED)}
    missing_required_exams = [x.code for x in job.required_exams.all() if x.pk not in required_passed]
    if missing_required_exams: hard_failures.append("Required passed exam missing.")
    if job.sponsorship_available is False and profile.requires_visa_sponsorship:
        hard_failures.append("Job explicitly does not offer sponsorship, but candidate requires it.")
        warnings.append("Sponsorship mismatch is a hard eligibility issue.")
    authorization = profile.employment_authorization_status.lower()
    if job.work_authorization_requirement != JobPosting.Authorization.ANY:
        if not authorization: hard_unknowns.append("Work authorization status is missing.")
        elif job.work_authorization_requirement == JobPosting.Authorization.US_CITIZEN and "citizen" not in authorization: hard_failures.append("U.S. citizenship requirement not met.")
        elif job.work_authorization_requirement == JobPosting.Authorization.PERMANENT_RESIDENT and not any(x in authorization for x in ("permanent", "green card")): hard_failures.append("Permanent-resident requirement not met.")
        elif job.work_authorization_requirement == JobPosting.Authorization.AUTHORIZED and any(x in authorization for x in ("not authorized", "require sponsorship")): hard_failures.append("Work authorization requirement not met.")
    degree_component = components["degree_major"]
    if job.degree_requirement in JOB_DEGREE_RANK and degree_component["score"] == 0:
        if _candidate_degree(profile, list(user.education_history.all())): hard_failures.append("Degree requirement not met.")
        else: hard_unknowns.append("Degree requirement cannot be confirmed.")
    if job.years_experience is not None:
        candidate_years = calculate_experience_years(user.work_experiences.all(), today=today)
        if candidate_years < Decimal(job.years_experience):
            hard_failures.append("Minimum experience requirement not met.")
    eligibility = JobMatch.Eligibility.NOT_ELIGIBLE if hard_failures else JobMatch.Eligibility.POSSIBLY_ELIGIBLE if hard_unknowns or warnings else JobMatch.Eligibility.ELIGIBLE
    applicable = [(MATCH_WEIGHTS[name], data["score"]) for name, data in components.items() if data["applicable"]]
    score = round(sum(weight * value for weight, value in applicable) / sum(weight for weight, _ in applicable)) if applicable else 50
    complete = profile_is_match_ready(user)
    return MatchResult(
        overall_score=score if complete else None,
        eligibility_status=eligibility,
        matched_items=matched,
        missing_items=missing,
        warnings=warnings,
        component_scores={name: data["score"] for name, data in components.items()},
        explanation={"components": components, "hard_failures": hard_failures, "hard_unknowns": hard_unknowns, "weights": MATCH_WEIGHTS},
        profile_complete=complete,
    )


def _hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def profile_fingerprint(user):
    profile = user.candidate_profile
    return _hash({
        "profile": {f.name: getattr(profile, f.name) for f in profile._meta.fields if f.name not in ("id", "created_at", "updated_at")},
        "areas": list(profile.preferred_practice_areas.values_list("pk", flat=True).order_by("pk")),
        "education": list(user.education_history.values().order_by("pk")),
        "exams": list(user.exams.values().order_by("pk")),
        "skills": list(user.skills.values().order_by("pk")),
        "experience": list(user.work_experiences.values().order_by("pk")),
    })


def job_fingerprint(job):
    return _hash({
        "job": {f.name: getattr(job, f.name) for f in job._meta.fields if f.name not in ("id", "created_at", "updated_at")},
        "areas": sorted(item.pk for item in job.practice_areas.all()),
        "required_exams": sorted(item.pk for item in job.required_exams.all()),
        "preferred_exams": sorted(item.pk for item in job.preferred_exams.all()),
        "required_skills": sorted(item.pk for item in job.required_skills.all()),
        "preferred_skills": sorted(item.pk for item in job.preferred_skills.all()),
    })


@transaction.atomic
def get_or_recalculate_match(user, job, force=False, profile_hash=None):
    profile_hash, job_hash = profile_hash or profile_fingerprint(user), job_fingerprint(job)
    existing = JobMatch.objects.filter(user=user, job=job).first()
    if existing and not force and existing.profile_fingerprint == profile_hash and existing.job_fingerprint == job_hash:
        return existing
    result = calculate_match(user, job)
    profile_time = user.candidate_profile.updated_at
    job_time = job.updated_at
    match, _ = JobMatch.objects.update_or_create(user=user, job=job, defaults={
        "score": result.overall_score or 0,
        "eligibility_status": result.eligibility_status,
        "explanation_json": result.as_json(),
        "profile_fingerprint": profile_hash,
        "job_fingerprint": job_hash,
        "profile_updated_at_snapshot": profile_time,
        "job_updated_at_snapshot": job_time,
    })
    return match


def recalculate_matches(*, users, jobs, force=True):
    results = []
    for user in users:
        current_profile_hash = profile_fingerprint(user)
        for job in jobs:
            results.append(get_or_recalculate_match(user, job, force=force, profile_hash=current_profile_hash))
    return results

from dataclasses import dataclass


@dataclass(frozen=True)
class CompletenessResult:
    percentage: int
    completed_sections: tuple[str, ...]
    missing_sections: tuple[str, ...]


def calculate_profile_completeness(user):
    profile = user.candidate_profile
    sections = {
        "Basic profile": all((profile.full_name, profile.city, profile.country)),
        "Education": bool(profile.university and profile.major) or user.education_history.exists(),
        "GPA": profile.gpa is not None or user.education_history.filter(gpa__isnull=False).exists(),
        "Actuarial exams": user.exams.exists(),
        "Skills": user.skills.exists(),
        "Work experience": user.work_experiences.exists(),
        "Career preferences": bool(
            profile.preferred_employment_type
            and profile.preferred_work_arrangement
            and profile.target_job_level
            and profile.preferred_practice_areas.exists()
        ),
        "Resume": bool(profile.resume),
    }
    completed = tuple(name for name, is_complete in sections.items() if is_complete)
    missing = tuple(name for name, is_complete in sections.items() if not is_complete)
    return CompletenessResult(round(len(completed) / len(sections) * 100), completed, missing)

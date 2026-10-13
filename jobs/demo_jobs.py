"""Clearly fictional job data safe for public demonstrations and tests."""

from django.db import transaction
from django.utils import timezone

from profiles.models import PracticeArea, Skill

from .models import Company, JobPosting, JobSource


DEMONSTRATION_JOBS = (
    {
        "company": "Northstar Life Demo Company (Fictional)",
        "industry": Company.Industry.INSURANCE,
        "external_job_id": "DEMO-NL-1001",
        "title": "Actuarial Internship — Fictional Demonstration",
        "description": (
            "A fictional summer internship supporting life actuarial analysis. "
            "The invented role prefers one actuarial exam and Excel experience. "
            "This record is demonstration data and is not a real opening."
        ),
        "location": "Hartford, CT",
        "city": "Hartford",
        "state_or_region": "Connecticut",
        "employment_type": JobPosting.EmploymentType.INTERNSHIP,
        "work_arrangement": JobPosting.WorkArrangement.HYBRID,
        "experience_level": JobPosting.ExperienceLevel.INTERNSHIP,
        "practice_areas": ("Life",),
        "preferred_skills": ("Excel",),
    },
    {
        "company": "Blue Harbor Re Demo Company (Fictional)",
        "industry": Company.Industry.REINSURANCE,
        "external_job_id": "DEMO-BH-1002",
        "title": "Corporate Reserving Intern — Fictional Demonstration",
        "description": (
            "A fictional reserving internship using invented requirements for UI "
            "and matching demonstrations. This is not a real opening."
        ),
        "location": "New York, NY",
        "city": "New York",
        "state_or_region": "New York",
        "employment_type": JobPosting.EmploymentType.INTERNSHIP,
        "work_arrangement": JobPosting.WorkArrangement.HYBRID,
        "experience_level": JobPosting.ExperienceLevel.INTERNSHIP,
        "practice_areas": ("Property & Casualty", "Reinsurance"),
        "preferred_skills": ("Excel",),
        "sponsorship_available": False,
    },
    {
        "company": "Summit Risk Demo Company (Fictional)",
        "industry": Company.Industry.CONSULTING,
        "external_job_id": "DEMO-SR-1003",
        "title": "Entry-Level Actuarial Analyst — Fictional Demonstration",
        "description": (
            "A fictional entry-level consulting role created solely for public "
            "demonstration and automated testing. This is not a real opening."
        ),
        "location": "Chicago, IL",
        "city": "Chicago",
        "state_or_region": "Illinois",
        "employment_type": JobPosting.EmploymentType.FULL_TIME,
        "work_arrangement": JobPosting.WorkArrangement.HYBRID,
        "experience_level": JobPosting.ExperienceLevel.ENTRY,
        "practice_areas": ("Actuarial Consulting",),
        "preferred_skills": ("Excel", "SQL"),
    },
    {
        "company": "Beacon Benefits Demo Company (Fictional)",
        "industry": Company.Industry.CONSULTING,
        "external_job_id": "DEMO-BB-1004",
        "title": "Benefits Actuarial Associate — Fictional Demonstration",
        "description": (
            "A fictional employee-benefits role with invented duties and data. "
            "This record does not represent an employer or live vacancy."
        ),
        "location": "Boston, MA",
        "city": "Boston",
        "state_or_region": "Massachusetts",
        "employment_type": JobPosting.EmploymentType.FULL_TIME,
        "work_arrangement": JobPosting.WorkArrangement.ONSITE,
        "experience_level": JobPosting.ExperienceLevel.ENTRY,
        "practice_areas": ("Employee Benefits",),
        "preferred_skills": ("Excel",),
        "years_experience": "1.0",
    },
    {
        "company": "Meridian Health Demo Company (Fictional)",
        "industry": Company.Industry.INSURANCE,
        "external_job_id": "DEMO-MH-1005",
        "title": "Senior Health Actuarial Analyst — Fictional Demonstration",
        "description": (
            "A fictional experienced health actuarial role for testing remote-work "
            "and experience matching. This is not a real opening."
        ),
        "location": "Remote — United States",
        "city": "",
        "state_or_region": "",
        "employment_type": JobPosting.EmploymentType.FULL_TIME,
        "work_arrangement": JobPosting.WorkArrangement.REMOTE,
        "experience_level": JobPosting.ExperienceLevel.EXPERIENCED,
        "practice_areas": ("Health",),
        "preferred_skills": ("Python", "Data Analysis"),
        "years_experience": "5.0",
    },
)


@transaction.atomic
def seed_demonstration_jobs():
    """Create or update only the namespaced fictional public demo records."""
    seeded_at = timezone.now()
    created_count = 0
    updated_count = 0
    seeded = []

    for record in DEMONSTRATION_JOBS:
        company, _ = Company.objects.update_or_create(
            name=record["company"],
            defaults={
                "website": "https://example.test/",
                "careers_url": "https://jobs.example.test/",
                "industry": record["industry"],
                "description": "Clearly fictional public demonstration data.",
                "active": True,
            },
        )
        source_name = f"{record['company']} — Fictional Public Demo"
        source, _ = JobSource.objects.update_or_create(
            name=source_name,
            defaults={
                "company": company,
                "source_type": JobSource.SourceType.MANUAL,
                "base_url": "https://jobs.example.test/",
                "enabled": False,
                "robots_policy_status": JobSource.ReviewStatus.NOT_APPLICABLE,
                "terms_review_status": JobSource.ReviewStatus.NOT_APPLICABLE,
                "notes": "Synthetic source. No employer site is contacted.",
                "last_sync_at": seeded_at,
                "last_success_at": seeded_at,
                "last_error": "",
            },
        )
        source_url = (
            f"https://jobs.example.test/fictional/{record['external_job_id'].lower()}"
        )
        defaults = {
            "company": company,
            "title": record["title"],
            "description": record["description"],
            "raw_source_text": record["description"],
            "location": record["location"],
            "city": record["city"],
            "state_or_region": record["state_or_region"],
            "country": "United States",
            "employment_type": record["employment_type"],
            "work_arrangement": record["work_arrangement"],
            "experience_level": record["experience_level"],
            "application_url": source_url,
            "source_url": source_url,
            "source_name": source_name,
            "active": True,
            "last_seen_at": seeded_at,
            "consecutive_missing_syncs": 0,
            "minimum_gpa": None,
            "degree_requirement": JobPosting.DegreeRequirement.UNSPECIFIED,
            "major_requirements": "",
            "work_authorization_requirement": JobPosting.Authorization.ANY,
            "sponsorship_available": record.get("sponsorship_available"),
            "years_experience": record.get("years_experience"),
        }
        job, created = JobPosting.objects.update_or_create(
            source=source,
            external_job_id=record["external_job_id"],
            defaults=defaults,
        )
        if job.first_seen_at is None:
            job.first_seen_at = seeded_at
            job.save(update_fields=("first_seen_at",))

        job.practice_areas.set(
            PracticeArea.objects.filter(
                name__in=record["practice_areas"], active=True
            )
        )
        job.required_skills.clear()
        job.preferred_skills.set(
            Skill.objects.filter(
                name__in=record.get("preferred_skills", ()), active=True
            )
        )
        job.required_exams.clear()
        job.preferred_exams.clear()

        created_count += int(created)
        updated_count += int(not created)
        seeded.append(job)

    return seeded, created_count, updated_count

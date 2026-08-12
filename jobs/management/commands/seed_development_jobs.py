from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from jobs.models import Company, JobPosting, JobSource
from profiles.models import ActuarialExam, PracticeArea, Skill


class Command(BaseCommand):
    help = "Seed clearly fictional companies and jobs for local UI testing only."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Development jobs can only be seeded when DEBUG=True.")
        source, _ = JobSource.objects.update_or_create(
            name="Development Seed Data",
            defaults={"source_type": JobSource.SourceType.MANUAL, "enabled": False},
        )
        companies = {}
        for name, industry, city in (
            ("Northstar Mutual (Fictional)", "insurance", "Hartford, CT"),
            ("Summit Actuarial Consulting (Fictional)", "consulting", "Chicago, IL"),
            ("Blue Harbor Re (Fictional)", "reinsurance", "New York, NY"),
        ):
            companies[name], _ = Company.objects.update_or_create(
                name=name,
                defaults={"industry": industry, "headquarters": city, "description": "Fictional development data for Actuary Career Match UI testing.", "active": True},
            )
        jobs = (
            ("DEV-NM-001", "Actuarial Internship — Development Data", "Northstar Mutual (Fictional)", "Hartford, CT", "internship", "hybrid", "internship", "Life", ["Excel", "Python"], 0),
            ("DEV-SA-001", "Entry-Level Actuarial Analyst — Development Data", "Summit Actuarial Consulting (Fictional)", "Chicago, IL", "full_time", "hybrid", "entry", "Actuarial Consulting", ["Excel", "SQL"], 0),
            ("DEV-BH-001", "Experienced Pricing Actuary — Development Data", "Blue Harbor Re (Fictional)", "Remote — United States", "full_time", "remote", "experienced", "Reinsurance", ["Python", "Data Analysis"], 5),
        )
        for external_id, title, company_name, location, employment, arrangement, level, area_name, skill_names, years_experience in jobs:
            job, _ = JobPosting.objects.update_or_create(
                source=source,
                external_job_id=external_id,
                defaults={
                    "company": companies[company_name], "title": title,
                    "description": "This is a fictional job created only for local development and manual UI testing. It is not a real opening.",
                    "location": location, "country": "United States", "employment_type": employment,
                    "work_arrangement": arrangement, "experience_level": level,
                    "source_name": "Development Seed Data — Fictional", "posted_at": timezone.now(),
                    "expires_at": timezone.now() + timedelta(days=90), "active": True,
                    "degree_requirement": "bachelor", "minimum_gpa": "3.00", "years_experience": years_experience,
                },
            )
            area = PracticeArea.objects.filter(name=area_name).first()
            if area:
                job.practice_areas.set([area])
            job.preferred_skills.set(Skill.objects.filter(name__in=skill_names))
            if level != "experienced":
                exam = ActuarialExam.objects.filter(organization="SOA", code="P").first()
                if exam:
                    job.preferred_exams.set([exam])
        self.stdout.write(self.style.SUCCESS("Fictional development companies and jobs seeded."))

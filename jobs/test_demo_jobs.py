from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from profiles.models import ActuarialExam, CandidateProfile, Skill, UserExam, UserSkill

from .demo_jobs import DEMONSTRATION_JOBS, seed_demonstration_jobs
from .matching import calculate_match
from .models import (
    ApplicationStatusHistory,
    Company,
    JobApplication,
    JobPosting,
    JobSource,
    SavedJob,
)


class DemonstrationJobTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_reference_data", verbosity=0)

    def make_existing_records(self):
        company = Company.objects.create(name="Existing Local Company (Test)")
        source = JobSource.objects.create(
            company=company,
            name="Existing Local Source (Test)",
            source_type=JobSource.SourceType.MANUAL,
        )
        job = JobPosting.objects.create(
            company=company,
            source=source,
            title="Existing Local Actuarial Job (Test)",
            description="Synthetic pre-existing test record.",
            external_job_id="EXISTING-TEST-1",
            active=True,
        )
        user = get_user_model().objects.create_user(
            username="demo-safety-user",
            email="demo-safety@example.com",
            password="StrongPass123!",
        )
        saved = SavedJob.objects.create(user=user, job=job)
        application = JobApplication.objects.create(user=user, job=job)
        return job, saved, application, application.status_history.get()

    def test_demo_seed_is_fictional_and_idempotent(self):
        seeded, created, updated = seed_demonstration_jobs()
        ids = [job.pk for job in seeded]

        seeded_again, created_again, updated_again = seed_demonstration_jobs()

        self.assertEqual(len(seeded), 5)
        self.assertEqual((created, updated), (5, 0))
        self.assertEqual((created_again, updated_again), (0, 5))
        self.assertEqual([job.pk for job in seeded_again], ids)
        self.assertEqual(JobPosting.objects.count(), 5)
        for job in seeded:
            self.assertIn("Fictional", job.company.name)
            self.assertIn("fictional", job.description.lower())
            self.assertEqual(job.source_url.split("/", 3)[2], "jobs.example.test")
            self.assertFalse(job.source.enabled)

    def test_demo_seed_preserves_existing_job_and_application_history(self):
        job, saved, application, history = self.make_existing_records()

        seed_demonstration_jobs()

        self.assertTrue(JobPosting.objects.filter(pk=job.pk).exists())
        self.assertTrue(SavedJob.objects.filter(pk=saved.pk, job=job).exists())
        self.assertTrue(
            JobApplication.objects.filter(pk=application.pk, job=job).exists()
        )
        self.assertTrue(
            ApplicationStatusHistory.objects.filter(pk=history.pk).exists()
        )

    def test_demo_jobs_render_and_match(self):
        jobs, _, _ = seed_demonstration_jobs()
        user = get_user_model().objects.create_user(
            username="demo-candidate",
            email="demo-candidate@example.com",
            password="StrongPass123!",
        )
        profile = CandidateProfile.objects.get(user=user)
        profile.full_name = "Demo Candidate"
        profile.city = "Hartford"
        profile.state_or_region = "Connecticut"
        profile.country = "United States"
        profile.degree_level = CandidateProfile.DegreeLevel.BACHELOR
        profile.major = "Actuarial Science"
        profile.preferred_employment_type = CandidateProfile.EmploymentType.INTERNSHIP
        profile.preferred_work_arrangement = CandidateProfile.WorkArrangement.HYBRID
        profile.target_job_level = CandidateProfile.JobLevel.INTERNSHIP
        profile.save()
        UserExam.objects.create(
            user=user,
            exam=ActuarialExam.objects.get(organization="SOA", code="P"),
            status=UserExam.Status.PASSED,
        )
        UserSkill.objects.create(
            user=user,
            skill=Skill.objects.get(name="Excel"),
            proficiency_level=UserSkill.Proficiency.INTERMEDIATE,
        )
        user.refresh_from_db()
        internship = next(
            job for job in jobs if job.external_job_id == "DEMO-NL-1001"
        )

        result = calculate_match(user, internship)
        response = self.client.get(reverse("jobs:detail", args=[internship.pk]))

        self.assertIsInstance(result.overall_score, int)
        self.assertContains(response, internship.title)
        self.assertContains(response, 'rel="noopener noreferrer nofollow"')

    def test_dataset_contains_only_reserved_urls_and_fictional_names(self):
        for record in DEMONSTRATION_JOBS:
            self.assertIn("Fictional", record["company"])
            self.assertTrue(record["external_job_id"].startswith("DEMO-"))

    @override_settings(DEBUG=True)
    def test_seed_command_is_available_for_local_development(self):
        call_command("seed_demo_jobs", verbosity=0)
        self.assertEqual(JobPosting.objects.count(), len(DEMONSTRATION_JOBS))

    @override_settings(DEBUG=False)
    def test_seed_command_refuses_non_debug_environments(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo_jobs", verbosity=0)

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from profiles.models import ActuarialExam, PracticeArea, Skill

from .models import Company, ImportRun, JobPosting, JobSource
from .services import import_from_adapter
from .sources import BaseJobSourceAdapter, ImportPayloadError, ImportedJob


class JobSystemTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Example Actuarial", industry="consulting")
        self.source = JobSource.objects.create(name="Manual Admin", source_type="manual")
        self.area = PracticeArea.objects.create(name="Life")
        self.exam = ActuarialExam.objects.create(organization="SOA", code="P", name="Probability")
        self.skill = Skill.objects.create(name="Python", category="programming")

    def make_job(self, **kwargs):
        defaults = {
            "company": self.company,
            "source": self.source,
            "title": "Actuarial Analyst",
            "description": "Analyze actuarial data and communicate results.",
            "location": "Hartford, CT",
            "country": "United States",
            "employment_type": "full_time",
            "work_arrangement": "hybrid",
            "experience_level": "entry",
            "external_job_id": "JOB-001",
            "active": True,
        }
        defaults.update(kwargs)
        return JobPosting.objects.create(**defaults)

    def test_company_creation(self):
        self.assertEqual(str(self.company), "Example Actuarial")
        self.assertTrue(self.company.active)

    def test_company_name_is_case_insensitively_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Company.objects.create(name="EXAMPLE ACTUARIAL")

    def test_job_creation_and_requirement_relationships(self):
        job = self.make_job()
        job.practice_areas.add(self.area)
        job.required_exams.add(self.exam)
        job.preferred_skills.add(self.skill)

        self.assertEqual(job.company, self.company)
        self.assertEqual(list(job.practice_areas.all()), [self.area])
        self.assertEqual(list(job.required_exams.all()), [self.exam])
        self.assertEqual(list(job.preferred_skills.all()), [self.skill])

    def test_active_inactive_expired_and_inactive_company_visibility(self):
        visible = self.make_job()
        inactive = self.make_job(external_job_id="JOB-002", title="Inactive", active=False)
        expired = self.make_job(external_job_id="JOB-003", title="Expired", expires_at=timezone.now() - timedelta(seconds=1))
        hidden_company = Company.objects.create(name="Hidden Company", active=False)
        company_job = self.make_job(company=hidden_company, external_job_id="JOB-004", title="Hidden company job")

        self.assertEqual(list(JobPosting.objects.visible()), [visible])
        for job in (inactive, expired, company_job):
            self.assertEqual(self.client.get(reverse("jobs:detail", args=[job.pk])).status_code, 404)

    def test_job_filtering(self):
        matching = self.make_job()
        matching.practice_areas.add(self.area)
        self.make_job(external_job_id="JOB-002", title="Remote Intern", location="Boston, MA", employment_type="internship", work_arrangement="remote", experience_level="internship")

        response = self.client.get(reverse("jobs:list"), {
            "company": self.company.pk,
            "location": "Hartford",
            "employment_type": "full_time",
            "work_arrangement": "hybrid",
            "experience_level": "entry",
            "practice_area": self.area.pk,
        })

        self.assertEqual(list(response.context["jobs"]), [matching])

    def test_job_keyword_search(self):
        self.make_job(title="Pricing Actuary", description="Build pricing models")
        self.make_job(external_job_id="JOB-002", title="Valuation Actuary", description="Reserve analysis")

        response = self.client.get(reverse("jobs:list"), {"keyword": "pricing"})

        self.assertContains(response, "Pricing Actuary")
        self.assertNotContains(response, "Valuation Actuary")

    def test_active_job_detail_is_public_and_escapes_untrusted_description(self):
        job = self.make_job(description='<script>alert("unsafe")</script>')

        response = self.client.get(reverse("jobs:detail", args=[job.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;", html=False)
        self.assertNotContains(response, '<script>alert("unsafe")</script>', html=False)

    def test_external_id_duplicate_prevention(self):
        self.make_job()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_job(title="Duplicate title")

    def test_fallback_duplicate_prevention(self):
        self.make_job(source=None, external_job_id="", source_url="https://example.com/jobs/one")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_job(source=None, external_job_id="", source_url="https://example.com/jobs/one")

    def test_import_source_tracking(self):
        run = ImportRun.objects.create(source=self.source, status="success", jobs_seen=3, jobs_created=2)
        self.assertEqual(self.source.import_runs.get(), run)
        self.assertEqual(run.records_created, 2)

    def test_job_validation_rejects_malformed_import_identity_and_salary(self):
        source = JobSource.objects.create(name="Authorized API", source_type="ats_api", enabled=True)
        job = self.make_job(source=source, external_job_id="", source_url="", salary_min=Decimal("100"), salary_max=Decimal("50"))
        with self.assertRaises(ValidationError):
            job.full_clean()

    def test_source_adapter_rejects_malformed_external_values(self):
        with self.assertRaises(ImportPayloadError):
            BaseJobSourceAdapter.validated_url("javascript:alert(1)", required=True)
        with self.assertRaises(ImportPayloadError):
            BaseJobSourceAdapter.decimal_or_none("not-a-number")


class FakeAdapter(BaseJobSourceAdapter):
    def fetch(self, limit=None):
        records = [{"id": "EXT-1"}]
        return records[:limit] if limit else records

    def normalize(self, raw_record):
        return ImportedJob(
            external_job_id=raw_record["id"],
            title="Imported Actuarial Analyst",
            description="Authorized structured feed record",
            source_url="https://jobs.example.test/EXT-1",
        )


class MalformedAdapter(FakeAdapter):
    def normalize(self, raw_record):
        raise ImportPayloadError("Malformed external record")


class ImportAndSeedTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Import Company")
        self.source = JobSource.objects.create(
            name="Test Feed", source_type="ats_api", enabled=True, company=self.company,
            robots_policy_status="allowed", terms_review_status="allowed",
        )

    def test_adapter_import_updates_instead_of_duplicating(self):
        defaults = {"employment_type": "full_time", "work_arrangement": "remote", "experience_level": "entry"}
        first = import_from_adapter(FakeAdapter(self.source), self.company, defaults)
        second = import_from_adapter(FakeAdapter(self.source), self.company, defaults)

        self.assertEqual(JobPosting.objects.count(), 1)
        self.assertEqual((first.records_created, first.records_updated), (1, 0))
        self.assertEqual((second.records_created, second.records_updated), (0, 1))
        self.source.refresh_from_db()
        self.assertIsNotNone(self.source.last_success_at)

    def test_disabled_source_is_skipped_without_fetching(self):
        self.source.enabled = False
        self.source.save(update_fields=("enabled",))
        adapter = FakeAdapter(self.source)
        from unittest.mock import patch
        with patch.object(adapter, "fetch") as fetch:
            run = import_from_adapter(adapter, self.company, {})
        fetch.assert_not_called()
        self.assertEqual(run.status, ImportRun.Status.SKIPPED)

    def test_malformed_import_is_tracked(self):
        defaults = {"employment_type": "full_time", "work_arrangement": "remote", "experience_level": "entry"}
        result = import_from_adapter(MalformedAdapter(self.source), self.company, defaults)
        run = ImportRun.objects.get()
        self.source.refresh_from_db()
        self.assertEqual(result.status, ImportRun.Status.PARTIAL)
        self.assertEqual(run.status, ImportRun.Status.PARTIAL)
        self.assertIn("Malformed external record", self.source.last_error)

    def test_job_list_is_paginated(self):
        for number in range(11):
            JobPosting.objects.create(
                company=self.company, source=self.source, external_job_id=f"PAGE-{number}",
                title=f"Job {number}", description="Development test", employment_type="full_time",
                work_arrangement="remote", experience_level="entry",
            )
        response = self.client.get(reverse("jobs:list"))
        self.assertEqual(len(response.context["jobs"]), 10)
        self.assertTrue(response.context["is_paginated"])

    @override_settings(DEBUG=True)
    def test_development_seed_is_fictional_and_idempotent(self):
        call_command("seed_reference_data", verbosity=0)
        call_command("seed_development_jobs", verbosity=0)
        first_counts = (Company.objects.count(), JobPosting.objects.count())
        call_command("seed_development_jobs", verbosity=0)

        self.assertEqual(first_counts, (4, 3))
        self.assertEqual((Company.objects.count(), JobPosting.objects.count()), first_counts)
        self.assertTrue(all("Fictional" in name for name in Company.objects.exclude(pk=self.company.pk).values_list("name", flat=True)))
        self.assertTrue(all("Development Data" in title for title in JobPosting.objects.values_list("title", flat=True)))
        experienced_job = JobPosting.objects.get(
            source__name="Development Seed Data",
            external_job_id="DEV-BH-001",
        )
        self.assertEqual(experienced_job.years_experience, Decimal("5.0"))
        response = self.client.get(reverse("jobs:detail", args=[experienced_job.pk]))
        self.assertContains(response, "5.0 years")

    @override_settings(DEBUG=False)
    def test_development_seed_refuses_non_debug_environment(self):
        from django.core.management import CommandError
        with self.assertRaises(CommandError):
            call_command("seed_development_jobs", verbosity=0)

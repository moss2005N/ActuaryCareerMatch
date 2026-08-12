import json
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from django.core.management import call_command
from django.test import TestCase, override_settings

from profiles.models import ActuarialExam, Skill

from .http import HTTPClientError, SourceHTTPClient
from .models import Company, ImportRun, JobPosting, JobSource
from .relevance import is_actuarial_relevant
from .requirements import extract_requirements
from .services import sync_source
from .sources import GreenhouseSourceAdapter, JSONFeedSourceAdapter, LeverSourceAdapter
from .sources.base import BaseJobSourceAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text())


class AdapterParsingTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Adapter Test Company")

    def source(self, source_type, **kwargs):
        return JobSource.objects.create(
            company=self.company, name=f"{source_type}-{JobSource.objects.count()}",
            source_type=source_type, enabled=True, robots_policy_status="allowed",
            terms_review_status="allowed", **kwargs,
        )

    def test_greenhouse_adapter_parsing(self):
        source = self.source("greenhouse", board_identifier="fixture")
        adapter = GreenhouseSourceAdapter(source, fixture_data=load_fixture("greenhouse_sample.json"))
        records = adapter.fetch()
        job = adapter.normalize(records[0])
        self.assertEqual(job.external_job_id, "900001")
        self.assertEqual(job.title, "Actuarial Analyst — Fixture")
        self.assertEqual(job.work_arrangement, "hybrid")
        self.assertNotIn("<p>", job.description)
        self.assertIsNone(job.posted_at)

    def test_lever_adapter_parsing(self):
        source = self.source("lever", board_identifier="fixture")
        adapter = LeverSourceAdapter(source, fixture_data=load_fixture("lever_sample.json"))
        job = adapter.normalize(adapter.fetch()[0])
        self.assertEqual(job.external_job_id, "fixture-lever-001")
        self.assertEqual(job.employment_type, "internship")
        self.assertEqual(job.work_arrangement, "hybrid")

    def test_json_feed_adapter_with_configurable_mapping(self):
        source = self.source("other_api", base_url="https://example.test/jobs", field_mapping={
            "list_path": "data.jobs", "external_job_id": "job.id", "title": "job.title",
            "description": "job.body", "source_url": "job.url", "location": "job.location",
        })
        fixture = {"data": {"jobs": [{"job": {
            "id": "JSON-1", "title": "Actuarial Consultant", "body": "Excel required",
            "url": "https://example.test/jobs/JSON-1", "location": "Boston, MA",
        }}]}}
        adapter = JSONFeedSourceAdapter(source, fixture_data=fixture)
        job = adapter.normalize(adapter.fetch()[0])
        self.assertEqual(job.external_job_id, "JSON-1")
        self.assertEqual(job.location, "Boston, MA")


class HTTPClientTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="HTTP Company")
        self.source = JobSource.objects.create(
            company=company, name="HTTP Source", source_type="other_api",
            request_timeout_seconds=3, minimum_request_interval_seconds=1,
        )

    def test_timeout_is_bounded_and_retried(self):
        opener = Mock()
        opener.open.side_effect = URLError("timeout")
        client = SourceHTTPClient(self.source, opener=opener, sleep=Mock(), max_retries=2)
        with self.assertRaises(HTTPClientError) as caught:
            client.get("https://example.test/jobs")
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(opener.open.call_count, 3)
        self.assertTrue(all(call.kwargs["timeout"] == 3 for call in opener.open.call_args_list))

    def test_retry_behavior_for_temporary_server_error(self):
        opener = Mock()
        response = Mock(read=Mock(return_value=b"{}"))
        opener.open.side_effect = [HTTPError("x", 503, "busy", {}, BytesIO()), response]
        sleeper = Mock()
        client = SourceHTTPClient(self.source, opener=opener, sleep=sleeper, max_retries=2)
        self.assertEqual(client.get("https://example.test/jobs"), b"{}")
        self.assertEqual(opener.open.call_count, 2)
        sleeper.assert_called()

    def test_403_is_blocking_and_never_retried(self):
        opener = Mock()
        opener.open.side_effect = HTTPError("x", 403, "blocked", {}, BytesIO())
        client = SourceHTTPClient(self.source, opener=opener, sleep=Mock(), max_retries=2)
        with self.assertRaises(HTTPClientError) as caught:
            client.get("https://example.test/jobs")
        self.assertTrue(caught.exception.blocked)
        self.assertEqual(opener.open.call_count, 1)

    def test_rate_limit_waits_between_requests(self):
        opener = Mock()
        opener.open.return_value = Mock(read=Mock(return_value=b"{}"))
        times = iter([0.0, 0.25, 0.25])
        sleeper = Mock()
        client = SourceHTTPClient(self.source, opener=opener, sleep=sleeper, monotonic=lambda: next(times))
        client.get("https://example.test/one")
        client.get("https://example.test/two")
        sleeper.assert_called_with(0.75)


class RelevanceAndRequirementTests(TestCase):
    def test_conservative_actuarial_relevance(self):
        self.assertTrue(is_actuarial_relevant("Pricing Actuary"))
        self.assertTrue(is_actuarial_relevant("Analyst", "Join our actuarial consulting team"))
        self.assertFalse(is_actuarial_relevant("Financial Analyst", "Analyze financial statements"))

    def test_rule_based_requirement_extraction(self):
        result = extract_requirements(
            "Requires a bachelor's degree, minimum GPA of 3.2, at least 5 years of experience, "
            "Exam P and FM, Excel, Python, SQL. Hybrid role. No visa sponsorship."
        )
        self.assertEqual(result.minimum_gpa, Decimal("3.2"))
        self.assertEqual(result.years_experience, Decimal("5"))
        self.assertEqual(result.exam_codes, ("FM", "P"))
        self.assertEqual(result.skill_names, ("Python", "Excel", "SQL"))
        self.assertEqual(result.degree_requirement, "bachelor")
        self.assertFalse(result.sponsorship_available)
        self.assertEqual(result.work_arrangement, "hybrid")

    def test_public_posting_requirement_phrases_are_explicitly_extracted(self):
        minimum = extract_requirements(
            "Experience: Minimum of 5 years of related experience. "
            "Education: Bachelor’s degree in Actuarial Science."
        )
        plus = extract_requirements("4+ years of quantitative analysis experience.")
        property_casualty = extract_requirements("10+ years of progressive P&C actuarial experience required.")

        self.assertEqual(minimum.years_experience, Decimal("5"))
        self.assertEqual(minimum.degree_requirement, "bachelor")
        self.assertEqual(plus.years_experience, Decimal("4"))
        self.assertEqual(property_casualty.years_experience, Decimal("10"))
        self.assertNotIn("P", property_casualty.exam_codes)


class SyncServiceTests(TestCase):
    def setUp(self):
        call_command("seed_reference_data", verbosity=0)
        self.company = Company.objects.create(name="Fixture Import Company")
        self.source = JobSource.objects.create(
            company=self.company, name="Fixture Greenhouse", source_type="greenhouse",
            board_identifier="fixture", enabled=True, robots_policy_status="allowed",
            terms_review_status="allowed", minimum_request_interval_seconds=0,
            missing_syncs_before_deactivation=3,
        )
        self.fixture = load_fixture("greenhouse_sample.json")

    def test_duplicate_update_counters_and_non_actuarial_skip(self):
        first = sync_source(self.source, fixture_data=self.fixture)
        second_fixture = load_fixture("greenhouse_sample.json")
        second_fixture["jobs"][0]["title"] = "Senior Actuarial Analyst — Fixture"
        second = sync_source(self.source, fixture_data=second_fixture)
        job = JobPosting.objects.get()
        self.assertEqual((first.jobs_created, first.jobs_skipped), (1, 1))
        self.assertEqual((second.jobs_updated, second.jobs_skipped), (1, 1))
        self.assertEqual(job.title, "Senior Actuarial Analyst — Fixture")
        self.assertIsNotNone(job.first_seen_at)
        self.assertIsNotNone(job.last_seen_at)
        self.assertEqual(ImportRun.objects.count(), 2)

    def test_sync_does_not_import_unrelated_title_that_only_mentions_actuarial(self):
        fixture = {"jobs": [{
            "id": 900003,
            "title": "Product Marketing Manager",
            "content": "Partner closely with product, finance, and actuarial teams.",
            "absolute_url": "https://example.test/jobs/900003",
            "location": {"name": "Remote"},
        }]}

        result = sync_source(self.source, fixture_data=fixture)

        self.assertEqual(result.jobs_seen, 1)
        self.assertEqual(result.jobs_skipped, 1)
        self.assertEqual(result.jobs_created, 0)
        self.assertFalse(JobPosting.objects.exists())

    def test_requirement_extraction_populates_existing_reference_relations(self):
        sync_source(self.source, fixture_data=self.fixture)
        job = JobPosting.objects.get()
        self.assertEqual(job.minimum_gpa, Decimal("3.00"))
        self.assertEqual(job.degree_requirement, "bachelor")
        self.assertFalse(job.sponsorship_available)
        self.assertEqual(set(job.preferred_skills.values_list("name", flat=True)), {"Excel", "Python"})
        self.assertEqual(set(job.preferred_exams.values_list("code", flat=True)), {"P"})

    def test_unspecified_requirements_remain_unknown(self):
        fixture = {"jobs": [{
            "id": 900004,
            "title": "Actuarial Analyst",
            "content": "Build actuarial models for clients.",
            "absolute_url": "https://example.test/jobs/900004",
            "location": {"name": "Boston, MA"},
        }]}

        sync_source(self.source, fixture_data=fixture)

        job = JobPosting.objects.get()
        self.assertEqual(job.degree_requirement, JobPosting.DegreeRequirement.UNSPECIFIED)
        self.assertIsNone(job.sponsorship_available)
        self.assertIsNone(job.years_experience)

    def test_dry_run_does_not_modify_database(self):
        result = sync_source(self.source, fixture_data=self.fixture, dry_run=True)
        self.assertEqual(result.jobs_seen, 2)
        self.assertEqual(JobPosting.objects.count(), 0)
        self.assertEqual(ImportRun.objects.count(), 0)
        self.source.refresh_from_db()
        self.assertIsNone(self.source.last_sync_at)

    def test_dry_run_can_review_a_disabled_source_without_enabling_or_writing(self):
        self.source.enabled = False
        self.source.save(update_fields=("enabled",))

        result = sync_source(self.source, fixture_data=self.fixture, dry_run=True)

        self.assertEqual(result.status, ImportRun.Status.SUCCESS)
        self.assertEqual(result.jobs_seen, 2)
        self.assertEqual(result.jobs_skipped, 1)
        self.assertEqual(JobPosting.objects.count(), 0)
        self.assertEqual(ImportRun.objects.count(), 0)
        self.source.refresh_from_db()
        self.assertFalse(self.source.enabled)
        self.assertIsNone(self.source.last_sync_at)

    def test_delayed_deactivation_requires_multiple_successful_absences(self):
        sync_source(self.source, fixture_data=self.fixture)
        empty = {"jobs": []}
        sync_source(self.source, fixture_data=empty)
        sync_source(self.source, fixture_data=empty)
        job = JobPosting.objects.get()
        self.assertTrue(job.active)
        self.assertEqual(job.consecutive_missing_syncs, 2)
        third = sync_source(self.source, fixture_data=empty)
        job.refresh_from_db()
        self.assertFalse(job.active)
        self.assertEqual(third.jobs_deactivated, 1)

    def test_disabled_source_skips_without_adapter_fetch(self):
        self.source.enabled = False
        self.source.save(update_fields=("enabled",))
        with patch("jobs.sources.greenhouse.GreenhouseSourceAdapter.fetch") as fetch:
            result = sync_source(self.source)
        fetch.assert_not_called()
        self.assertEqual(result.status, ImportRun.Status.SKIPPED)

    def test_fixture_management_command_dry_run(self):
        call_command(
            "sync_job_source", self.source.pk, "--dry-run", "--fixture",
            str(FIXTURES / "greenhouse_sample.json"), verbosity=0,
        )
        self.assertEqual(JobPosting.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_fixture_source_setup_is_local_and_idempotent(self):
        with patch("jobs.http.SourceHTTPClient.get") as network:
            call_command("seed_fixture_job_sources", verbosity=0)
            call_command("seed_fixture_job_sources", verbosity=0)
        network.assert_not_called()
        self.assertEqual(JobSource.objects.filter(board_identifier="local-fixture").count(), 2)

    def test_blocking_response_disables_source(self):
        class BlockedAdapter(BaseJobSourceAdapter):
            def fetch(self, limit=None):
                raise HTTPClientError("Source access stopped with HTTP 403.", status_code=403, blocked=True)

            def normalize(self, raw_record):
                raise AssertionError("No record should be normalized")

        result = sync_source(self.source, adapter_class=BlockedAdapter)
        self.source.refresh_from_db()
        self.assertEqual(result.status, ImportRun.Status.FAILED)
        self.assertFalse(self.source.enabled)

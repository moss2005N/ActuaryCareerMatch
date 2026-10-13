from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from profiles.models import ActuarialExam, Education, PracticeArea, Skill, UserExam, UserSkill, WorkExperience

from .matching import MATCH_WEIGHTS, calculate_experience_years, calculate_match, get_or_recalculate_match
from .models import Company, JobMatch, JobPosting, JobSource

User = get_user_model()


class MatchingTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("candidate", "candidate@example.com", "password-2026")
        self.profile = self.user.candidate_profile
        self.profile.full_name = "Candidate Example"
        self.profile.city = "Hartford"
        self.profile.state_or_region = "CT"
        self.profile.country = "United States"
        self.profile.preferred_locations = "Hartford, CT\nBoston, MA"
        self.profile.degree_level = "bachelor"
        self.profile.major = "Actuarial Science"
        self.profile.gpa = Decimal("3.60")
        self.profile.preferred_employment_type = "full_time"
        self.profile.preferred_work_arrangement = "remote"
        self.profile.target_job_level = "entry"
        self.profile.employment_authorization_status = "Authorized to work"
        self.profile.save()
        self.area = PracticeArea.objects.create(name="Health")
        self.other_area = PracticeArea.objects.create(name="Life")
        self.profile.preferred_practice_areas.add(self.area)
        self.exam_p = ActuarialExam.objects.create(organization="SOA", code="P", name="Probability")
        self.exam_fm = ActuarialExam.objects.create(organization="SOA", code="FM", name="Financial Mathematics")
        self.python = Skill.objects.create(name="Python", category="programming")
        self.sql = Skill.objects.create(name="SQL", category="data")
        UserExam.objects.create(user=self.user, exam=self.exam_p, status="passed", passed_date=date(2025, 1, 1))
        UserSkill.objects.create(user=self.user, skill=self.python, proficiency_level="expert", years_experience=3)
        Education.objects.create(user=self.user, institution="University", degree="BS", major="Actuarial Science", gpa=Decimal("3.60"))
        WorkExperience.objects.create(user=self.user, company="Insurer", job_title="Analyst", start_date=date(2023, 1, 1), end_date=date(2025, 1, 1))
        self.company = Company.objects.create(name="Real Test Company")
        self.source = JobSource.objects.create(company=self.company, name="Real Public Source", source_type="greenhouse", board_identifier="real")

    def make_job(self, **kwargs):
        defaults = dict(company=self.company, source=self.source, external_job_id="MATCH-1", title="Actuarial Analyst", description="Actuarial role", location="Remote", employment_type="full_time", work_arrangement="remote", experience_level="entry", minimum_gpa=Decimal("3.20"), degree_requirement="bachelor", years_experience=Decimal("2.0"))
        defaults.update(kwargs)
        job = JobPosting.objects.create(**defaults)
        job.practice_areas.add(self.area)
        job.required_exams.add(self.exam_p)
        job.required_skills.add(self.python)
        return job


class MatchingServiceTests(MatchingTestBase):
    def test_weights_total_one_hundred_and_perfect_match(self):
        self.assertEqual(sum(MATCH_WEIGHTS.values()), 100)
        result = calculate_match(self.user, self.make_job(), today=date(2025, 1, 1))
        self.assertEqual(result.overall_score, 100)
        self.assertEqual(result.eligibility_status, JobMatch.Eligibility.ELIGIBLE)

    def test_poor_match_and_target_level_mismatch(self):
        self.profile.gpa = Decimal("2.50"); self.profile.target_job_level = "internship"; self.profile.save()
        job = self.make_job(experience_level="experienced", years_experience=Decimal("10"))
        job.practice_areas.set([self.other_area]); job.required_exams.set([self.exam_fm]); job.required_skills.set([self.sql])
        result = calculate_match(self.user, job, today=date(2025, 1, 1))
        self.assertLess(result.overall_score, 35)
        self.assertEqual(result.eligibility_status, JobMatch.Eligibility.NOT_ELIGIBLE)
        self.assertTrue(any("Target level" in item for item in result.warnings))

    def test_missing_job_requirements_are_neutral(self):
        job = self.make_job(minimum_gpa=None, years_experience=None, degree_requirement="unspecified", employment_type="", work_arrangement="", experience_level="", location="")
        job.practice_areas.clear(); job.required_exams.clear(); job.required_skills.clear()
        result = calculate_match(self.user, job)
        self.assertIsNone(result.component_scores["gpa"])
        self.assertIsNone(result.component_scores["experience"])
        self.assertEqual(result.overall_score, 50)

    def test_missing_candidate_data_suppresses_precise_score(self):
        user = User.objects.create_user("incomplete", "incomplete@example.com", "password")
        result = calculate_match(user, self.make_job())
        self.assertIsNone(result.overall_score)
        self.assertFalse(result.profile_complete)

    def test_gpa_above_slightly_below_and_far_below(self):
        job = self.make_job(minimum_gpa=Decimal("3.70"))
        result = calculate_match(self.user, job)
        self.assertEqual(result.component_scores["gpa"], 60)
        self.profile.gpa = Decimal("3.0"); self.profile.save()
        self.assertEqual(calculate_match(self.user, job).component_scores["gpa"], 15)

    def test_exam_passed_studying_registered_and_missing_required(self):
        job = self.make_job(); job.required_exams.clear(); job.preferred_exams.add(self.exam_fm)
        record = UserExam.objects.create(user=self.user, exam=self.exam_fm, status="studying")
        self.assertEqual(calculate_match(self.user, job).component_scores["exams"], 55)
        record.status = "registered"; record.save()
        self.assertEqual(calculate_match(self.user, job).component_scores["exams"], 65)
        job.preferred_exams.clear(); job.required_exams.add(self.exam_fm)
        result = calculate_match(self.user, job)
        self.assertEqual(result.component_scores["exams"], 0)
        self.assertEqual(result.eligibility_status, JobMatch.Eligibility.NOT_ELIGIBLE)

    def test_required_and_preferred_skill_scoring(self):
        job = self.make_job(); job.required_skills.set([self.sql]); job.preferred_skills.add(self.python)
        result = calculate_match(self.user, job)
        self.assertEqual(result.component_scores["skills"], 50)
        self.assertTrue(any("Required skill SQL" in item for item in result.warnings))

    def test_experience_above_below_and_overlaps_are_not_double_counted(self):
        WorkExperience.objects.create(user=self.user, company="Overlap", job_title="Analyst", start_date=date(2024, 1, 1), end_date=date(2026, 1, 1))
        years = calculate_experience_years(self.user.work_experiences.all(), today=date(2026, 1, 1))
        self.assertGreaterEqual(years, Decimal("3.0")); self.assertLess(years, Decimal("3.1"))
        self.assertEqual(calculate_match(self.user, self.make_job(years_experience=Decimal("2")), today=date(2026, 1, 1)).component_scores["experience"], 100)
        self.assertLess(calculate_match(self.user, self.make_job(external_job_id="MATCH-2", years_experience=Decimal("6")), today=date(2026, 1, 1)).component_scores["experience"], 100)

    def test_practice_employment_location_and_remote_matching(self):
        result = calculate_match(self.user, self.make_job())
        self.assertEqual(result.component_scores["practice_area"], 100)
        self.assertEqual(result.component_scores["employment_level"], 100)
        self.assertEqual(result.component_scores["location"], 100)
        self.assertEqual(result.component_scores["work_arrangement"], 100)

    def test_senior_actuarial_analyst_is_matched_as_experienced_not_internship(self):
        job = self.make_job(
            title="Senior Actuarial Analyst",
            experience_level=JobPosting.ExperienceLevel.EXPERIENCED,
        )

        result = calculate_match(self.user, job)

        self.assertEqual(job.experience_level, JobPosting.ExperienceLevel.EXPERIENCED)
        self.assertEqual(result.component_scores["employment_level"], 60)

    def test_sponsorship_mismatch_and_unknown_sponsorship(self):
        self.profile.requires_visa_sponsorship = True; self.profile.save()
        blocked = calculate_match(self.user, self.make_job(sponsorship_available=False))
        unknown = calculate_match(self.user, self.make_job(external_job_id="MATCH-2", sponsorship_available=None))
        self.assertEqual(blocked.eligibility_status, JobMatch.Eligibility.NOT_ELIGIBLE)
        self.assertNotEqual(unknown.eligibility_status, JobMatch.Eligibility.NOT_ELIGIBLE)

    def test_degree_and_major_match_and_mismatch(self):
        job = self.make_job(major_requirements="Actuarial Science\nMathematics")
        self.assertEqual(calculate_match(self.user, job).component_scores["degree_major"], 100)
        self.profile.degree_level = "associate"; self.profile.major = "History"; self.profile.save()
        self.user.education_history.all().delete()
        result = calculate_match(self.user, job)
        self.assertEqual(result.component_scores["degree_major"], 0)
        self.assertEqual(result.eligibility_status, JobMatch.Eligibility.NOT_ELIGIBLE)


class MatchPersistenceAndViewTests(MatchingTestBase):
    def test_recommended_page_deduplicates_identical_metadata_badges(self):
        self.profile.preferred_employment_type = "internship"
        self.profile.target_job_level = "internship"
        self.profile.save()
        self.make_job(employment_type="internship", experience_level="internship")
        self.client.force_login(self.user)

        response = self.client.get(reverse("jobs:recommended"))

        self.assertContains(response, ">Internship</span>", count=1, html=False)

    def test_duplicate_job_match_prevention(self):
        job = self.make_job(); match = get_or_recalculate_match(self.user, job)
        with self.assertRaises(IntegrityError), transaction.atomic():
            JobMatch.objects.create(user=self.user, job=job, score=50, eligibility_status="eligible", explanation_json={}, profile_fingerprint="x", job_fingerprint="y", profile_updated_at_snapshot=match.profile_updated_at_snapshot, job_updated_at_snapshot=match.job_updated_at_snapshot)

    def test_recalculation_after_profile_and_job_changes(self):
        job = self.make_job(); first = get_or_recalculate_match(self.user, job); first_time = first.calculated_at
        self.profile.gpa = Decimal("2.0"); self.profile.save()
        second = get_or_recalculate_match(self.user, job)
        self.assertNotEqual(first.profile_fingerprint, second.profile_fingerprint)
        prior_job_hash = second.job_fingerprint
        job.minimum_gpa = Decimal("2.0"); job.save()
        third = get_or_recalculate_match(self.user, job)
        self.assertNotEqual(prior_job_hash, third.job_fingerprint)
        self.assertEqual(JobMatch.objects.count(), 1)

    def test_anonymous_privacy_and_public_browsing(self):
        job = self.make_job()
        list_response = self.client.get(reverse("jobs:list")); detail_response = self.client.get(reverse("jobs:detail", args=[job.pk]))
        self.assertEqual(list_response.status_code, 200)
        self.assertNotContains(list_response, "% match")
        self.assertContains(detail_response, "Sign in to see your match")
        self.assertFalse(JobMatch.objects.exists())

    def test_incomplete_profile_behavior(self):
        user = User.objects.create_user("empty", "empty@example.com", "password"); self.client.force_login(user); self.make_job()
        response = self.client.get(reverse("jobs:recommended"))
        self.assertContains(response, "Complete your profile to receive reliable job matches")
        self.assertNotContains(response, "% Match")

    def test_recommendation_ordering_and_authenticated_integrations(self):
        strong = self.make_job(title="Strong Match")
        weak = self.make_job(external_job_id="MATCH-2", title="Weak Match", experience_level="experienced", years_experience=Decimal("10"), minimum_gpa=Decimal("4.0"))
        weak.practice_areas.set([self.other_area]); weak.required_exams.set([self.exam_fm]); weak.required_skills.set([self.sql])
        self.client.force_login(self.user)
        response = self.client.get(reverse("jobs:recommended"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([m.job for m in response.context["recommendations"]], [strong, weak])
        self.assertContains(self.client.get(reverse("jobs:list")), "% match")
        self.assertContains(self.client.get(reverse("jobs:detail", args=[strong.pk])), "Your Match")

    def test_recalculation_command_supports_user_and_job(self):
        job = self.make_job()
        call_command("recalculate_job_matches", user=self.user.pk, job=job.pk, verbosity=0)
        self.assertTrue(JobMatch.objects.filter(user=self.user, job=job).exists())

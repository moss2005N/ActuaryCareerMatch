from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from profiles.models import ActuarialExam, Education, Skill, UserExam, UserSkill

from .models import ApplicationStatusHistory, Company, JobApplication, JobPosting, JobSource, SavedJob
from .workflow import save_application

User = get_user_model()


class JobWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("workflow-owner", "workflow@example.com", "password")
        self.other = User.objects.create_user("workflow-other", "other@example.com", "password")
        self.company = Company.objects.create(name="Workflow Company")
        self.other_company = Company.objects.create(name="Other Workflow Company")
        self.source = JobSource.objects.create(company=self.company, name="Workflow Source", source_type="manual")
        self.job = JobPosting.objects.create(company=self.company, source=self.source, title="Actuarial Analyst", description="Public description", location="Boston", employment_type="full_time", work_arrangement="remote", experience_level="entry", external_job_id="WF-1", application_url="https://company.example/apply/WF-1")

    def login(self):
        self.client.force_login(self.user)

    def test_save_duplicate_prevention_and_unsave_does_not_delete_job(self):
        self.login(); url = reverse("jobs:save", args=[self.job.pk])
        self.client.post(url); self.client.post(url)
        self.assertEqual(SavedJob.objects.filter(user=self.user, job=self.job).count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic(): SavedJob.objects.create(user=self.user, job=self.job)
        self.client.post(reverse("jobs:unsave", args=[self.job.pk]))
        self.assertFalse(SavedJob.objects.exists()); self.assertTrue(JobPosting.objects.filter(pk=self.job.pk).exists())

    def test_anonymous_save_redirect_and_safe_next(self):
        response = self.client.post(reverse("jobs:save", args=[self.job.pk]), {"next": "https://evil.example/steal"})
        expected = f"{reverse('accounts:login')}?next={reverse('jobs:detail', args=[self.job.pk])}"
        self.assertRedirects(response, expected, fetch_redirect_response=False)
        self.assertFalse(SavedJob.objects.exists())

    def test_anonymous_tracking_redirects_to_login_with_safe_job_detail_next(self):
        response = self.client.post(reverse("jobs:start_tracking", args=[self.job.pk]), {"next": "https://evil.example/"})
        expected = f"{reverse('accounts:login')}?next={reverse('jobs:detail', args=[self.job.pk])}"
        self.assertRedirects(response, expected, fetch_redirect_response=False)
        self.assertFalse(JobApplication.objects.exists())

    def test_create_application_ensures_saved_and_records_initial_history(self):
        self.login(); response = self.client.post(reverse("jobs:start_tracking", args=[self.job.pk]))
        application = JobApplication.objects.get(user=self.user, job=self.job)
        self.assertRedirects(response, reverse("jobs:application_edit", args=[application.pk]))
        self.assertTrue(SavedJob.objects.filter(user=self.user, job=self.job).exists())
        history = application.status_history.get(); self.assertEqual((history.old_status, history.new_status), ("", "interested"))
        self.assertEqual(application.external_application_url_snapshot, self.job.application_url)

    def test_application_ownership_and_other_user_cannot_view_or_edit(self):
        application = save_application(JobApplication(user=self.user, job=self.job))
        self.client.force_login(self.other)
        url = reverse("jobs:application_edit", args=[application.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"status": "offer", "notes": "stolen"}).status_code, 404)
        application.refresh_from_db(); self.assertEqual(application.status, "interested")

    def test_status_update_writes_history_and_private_notes(self):
        application = save_application(JobApplication(user=self.user, job=self.job)); self.login()
        response = self.client.post(reverse("jobs:application_edit", args=[application.pk]), {"status": "interview", "applied_at": timezone.localdate(), "follow_up_date": timezone.localdate() + timedelta(days=2), "notes": "Private compensation details"})
        self.assertRedirects(response, reverse("jobs:application_edit", args=[application.pk]))
        application.refresh_from_db(); self.assertEqual(application.status, "interview"); self.assertEqual(application.notes, "Private compensation details")
        history = application.status_history.first(); self.assertEqual((history.old_status, history.new_status), ("interested", "interview"))
        self.client.logout(); self.assertNotContains(self.client.get(reverse("jobs:detail", args=[self.job.pk])), "Private compensation details")
        self.assertNotContains(self.client.get(reverse("jobs:list")), "Private compensation details")

    def test_mark_as_applied_is_explicit_and_preserves_application_after_unsave(self):
        self.login(); self.client.post(reverse("jobs:mark_applied", args=[self.job.pk]))
        application = JobApplication.objects.get(); self.assertEqual(application.status, "applied"); self.assertEqual(application.applied_at, timezone.localdate()); self.assertTrue(SavedJob.objects.exists())
        self.client.post(reverse("jobs:unsave", args=[self.job.pk])); self.assertFalse(SavedJob.objects.exists()); self.assertTrue(JobApplication.objects.filter(pk=application.pk).exists())

    def test_future_applied_date_and_note_length_are_rejected(self):
        application = save_application(JobApplication(user=self.user, job=self.job)); self.login(); url = reverse("jobs:application_edit", args=[application.pk])
        response = self.client.post(url, {"status": "applied", "applied_at": timezone.localdate() + timedelta(days=1), "notes": "x" * 5001})
        self.assertContains(response, "Application date cannot be in the future"); self.assertContains(response, "at most 5000 characters")
        application.refresh_from_db(); self.assertEqual(application.status, "interested")

    def test_follow_up_and_overdue_display_and_filter(self):
        application = save_application(JobApplication(user=self.user, job=self.job, status="applied", applied_at=timezone.localdate(), follow_up_date=timezone.localdate() - timedelta(days=1)))
        self.login(); response = self.client.get(reverse("jobs:my_jobs"), {"follow_up": "due"})
        self.assertContains(response, "due/overdue"); self.assertContains(response, self.job.title)
        response = self.client.get(reverse("jobs:my_jobs"), {"follow_up": "upcoming"}); self.assertNotContains(response, self.job.title)

    def test_closed_inactive_job_is_retained_in_dashboard(self):
        save_application(JobApplication(user=self.user, job=self.job)); self.job.active = False; self.job.save(update_fields=("active",))
        self.login(); response = self.client.get(reverse("jobs:my_jobs"))
        self.assertContains(response, self.job.title); self.assertContains(response, "Posting inactive / closed")
        application = JobApplication.objects.get(); self.assertEqual(self.client.get(reverse("jobs:application_edit", args=[application.pk])).status_code, 200)

    def test_public_browsing_and_company_apply_link_are_unchanged(self):
        list_response = self.client.get(reverse("jobs:list")); detail_response = self.client.get(reverse("jobs:detail", args=[self.job.pk]))
        self.assertEqual(list_response.status_code, 200); self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, self.job.application_url); self.assertContains(detail_response, "Apply on company site")
        self.assertFalse(JobApplication.objects.exists())

    def test_job_list_shows_saved_and_application_status_only_to_owner(self):
        SavedJob.objects.create(user=self.user, job=self.job); save_application(JobApplication(user=self.user, job=self.job, status="preparing")); self.login()
        response = self.client.get(reverse("jobs:list")); self.assertContains(response, "Saved"); self.assertContains(response, "Application: Preparing")
        self.client.force_login(self.other); response = self.client.get(reverse("jobs:list")); self.assertNotContains(response, "Application: Preparing")

    def test_my_jobs_status_company_and_tracking_filters(self):
        application = save_application(JobApplication(user=self.user, job=self.job, status="interview"))
        second = JobPosting.objects.create(company=self.other_company, source=self.source, title="Second Actuarial Role", description="Role", external_job_id="WF-2")
        SavedJob.objects.create(user=self.user, job=second)
        self.login()
        self.assertContains(self.client.get(reverse("jobs:my_jobs"), {"status": "interview"}), self.job.title)
        self.assertNotContains(self.client.get(reverse("jobs:my_jobs"), {"status": "interview"}), second.title)
        self.assertContains(self.client.get(reverse("jobs:my_jobs"), {"company": self.other_company.pk}), second.title)
        self.assertContains(self.client.get(reverse("jobs:my_jobs"), {"tracking": "saved"}), second.title)
        self.assertNotContains(self.client.get(reverse("jobs:my_jobs"), {"tracking": "applied"}), second.title)

    def test_recommendation_page_includes_save_and_application_status(self):
        profile = self.user.candidate_profile; profile.full_name = "Workflow Owner"; profile.city = "Boston"; profile.degree_level = "bachelor"; profile.major = "Math"; profile.preferred_employment_type = "full_time"; profile.preferred_work_arrangement = "remote"; profile.target_job_level = "entry"; profile.save()
        exam = ActuarialExam.objects.create(organization="SOA", code="P", name="Probability"); skill = Skill.objects.create(name="Python", category="programming")
        UserExam.objects.create(user=self.user, exam=exam, status="planned"); UserSkill.objects.create(user=self.user, skill=skill, proficiency_level="beginner")
        save_application(JobApplication(user=self.user, job=self.job, status="preparing")); self.login()
        response = self.client.get(reverse("jobs:recommended")); self.assertContains(response, "Application: Preparing"); self.assertContains(response, "Saved")

    def test_dashboard_metrics(self):
        save_application(JobApplication(user=self.user, job=self.job, status="offer")); self.login(); response = self.client.get(reverse("jobs:my_jobs"))
        self.assertEqual(response.context["metrics"]["saved"], 1); self.assertEqual(response.context["metrics"]["offers"], 1)

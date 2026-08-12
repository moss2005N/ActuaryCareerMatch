import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import (
    ActuarialExam,
    Education,
    PracticeArea,
    Skill,
    UserExam,
    UserSkill,
    WorkExperience,
    private_resume_storage,
)
from .services import calculate_profile_completeness

User = get_user_model()


class ProfilePermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner", email="owner@example.com", password="test-password-2026"
        )
        self.other_user = User.objects.create_user(username="other", email="other@example.com")

    def test_anonymous_user_cannot_view_profile(self):
        response = self.client.get(reverse("profiles:detail"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('profiles:detail')}",
        )

    def test_authenticated_user_views_own_profile(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("profiles:detail"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["profile"].user, self.user)

    def test_user_can_only_edit_own_profile(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profiles:edit"),
            {
                "full_name": "Profile Owner",
                "city": "Hartford",
                "country": "United States",
            },
        )

        self.assertRedirects(response, reverse("profiles:detail"))
        self.user.candidate_profile.refresh_from_db()
        self.other_user.candidate_profile.refresh_from_db()
        self.assertEqual(self.user.candidate_profile.full_name, "Profile Owner")
        self.assertEqual(self.other_user.candidate_profile.full_name, "")


class PhaseTwoProfileTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.resume_directory = tempfile.TemporaryDirectory()
        private_resume_storage._location = cls.resume_directory.name
        private_resume_storage.__dict__.pop("base_location", None)
        private_resume_storage.__dict__.pop("location", None)

    @classmethod
    def tearDownClass(cls):
        cls.resume_directory.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user("owner2", "owner2@example.com", "test-password-2026")
        self.other = User.objects.create_user("other2", "other2@example.com", "test-password-2026")
        self.exam = ActuarialExam.objects.create(organization="SOA", code="P", name="Probability")
        self.skill = Skill.objects.create(name="Python", category="programming")
        self.client.force_login(self.user)

    def test_exam_creation_is_owned_by_logged_in_user(self):
        response = self.client.post(reverse("profiles:exams"), {
            "exam": self.exam.pk,
            "status": "studying",
            "planned_exam_date": "2027-01-15",
            "notes": "Weekly study plan",
        })
        self.assertRedirects(response, reverse("profiles:exams"))
        self.assertEqual(UserExam.objects.get().user, self.user)

    def test_duplicate_exam_is_prevented(self):
        UserExam.objects.create(user=self.user, exam=self.exam, status="planned")
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserExam.objects.create(user=self.user, exam=self.exam, status="studying")

    def test_exam_status_date_validation(self):
        record = UserExam(
            user=self.user,
            exam=self.exam,
            status=UserExam.Status.PASSED,
            planned_exam_date=date(2027, 1, 1),
        )
        with self.assertRaises(ValidationError):
            record.full_clean()

    def test_skill_creation_is_owned_by_logged_in_user(self):
        response = self.client.post(reverse("profiles:skills"), {
            "skill": self.skill.pk,
            "proficiency_level": "advanced",
            "years_experience": "2.5",
        })
        self.assertRedirects(response, reverse("profiles:skills"))
        self.assertEqual(UserSkill.objects.get().user, self.user)

    def test_duplicate_skill_is_prevented(self):
        UserSkill.objects.create(user=self.user, skill=self.skill, proficiency_level="beginner")
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserSkill.objects.create(user=self.user, skill=self.skill, proficiency_level="advanced")

    def test_education_records_are_owner_scoped(self):
        own = Education.objects.create(user=self.user, institution="Own University", degree="BS", major="Actuarial Science")
        other = Education.objects.create(user=self.other, institution="Other University", degree="BS", major="Mathematics")

        response = self.client.get(reverse("profiles:education"))

        self.assertContains(response, own.institution)
        self.assertNotContains(response, other.institution)
        self.assertEqual(self.client.get(reverse("profiles:education_edit", args=[other.pk])).status_code, 404)

    def test_work_experience_date_validation(self):
        record = WorkExperience(
            user=self.user,
            company="Insurer",
            job_title="Intern",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 7, 1),
        )
        with self.assertRaises(ValidationError):
            record.full_clean()
        record.end_date = date(2026, 9, 1)
        record.currently_working = True
        with self.assertRaises(ValidationError):
            record.full_clean()

    def test_resume_accepts_pdf_and_is_private(self):
        upload = SimpleUploadedFile("resume.pdf", b"%PDF-1.4\nprofile", content_type="application/pdf")
        response = self.client.post(reverse("profiles:resume"), {"resume": upload})
        self.assertRedirects(response, reverse("profiles:resume"))
        self.user.candidate_profile.refresh_from_db()
        self.assertEqual(self.user.candidate_profile.resume_filename, "resume.pdf")

        self.client.force_login(self.other)
        response = self.client.get(reverse("profiles:resume_download"))
        self.assertRedirects(response, reverse("profiles:resume"))

    def test_resume_rejects_non_pdf_extension_mime_and_signature(self):
        bad_extension = SimpleUploadedFile("resume.txt", b"%PDF-1.4", content_type="application/pdf")
        response = self.client.post(reverse("profiles:resume"), {"resume": bad_extension})
        self.assertContains(response, "File extension")

        bad_mime = SimpleUploadedFile("resume.pdf", b"%PDF-1.4", content_type="text/plain")
        response = self.client.post(reverse("profiles:resume"), {"resume": bad_mime})
        self.assertContains(response, "PDF MIME type")

        bad_signature = SimpleUploadedFile("resume.pdf", b"not a pdf", content_type="application/pdf")
        response = self.client.post(reverse("profiles:resume"), {"resume": bad_signature})
        self.assertContains(response, "not a valid PDF")

    def test_resume_rejects_files_larger_than_five_mb(self):
        upload = SimpleUploadedFile(
            "resume.pdf",
            b"%PDF-" + b"x" * (5 * 1024 * 1024),
            content_type="application/pdf",
        )
        response = self.client.post(reverse("profiles:resume"), {"resume": upload})
        self.assertContains(response, "5 MB or smaller")

    def test_users_cannot_edit_another_users_records(self):
        exam_record = UserExam.objects.create(user=self.other, exam=self.exam, status="planned")
        skill_record = UserSkill.objects.create(user=self.other, skill=self.skill, proficiency_level="beginner")
        education = Education.objects.create(user=self.other, institution="Other", degree="BS", major="Math")
        experience = WorkExperience.objects.create(user=self.other, company="Other Co", job_title="Analyst", start_date=date(2025, 1, 1))

        urls = [
            reverse("profiles:exam_edit", args=[exam_record.pk]),
            reverse("profiles:skill_edit", args=[skill_record.pk]),
            reverse("profiles:education_edit", args=[education.pk]),
            reverse("profiles:experience_edit", args=[experience.pk]),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_profile_completeness_service(self):
        self.assertEqual(calculate_profile_completeness(self.user).percentage, 0)
        profile = self.user.candidate_profile
        profile.full_name = "Candidate Owner"
        profile.city = "Hartford"
        profile.country = "United States"
        profile.university = "University"
        profile.major = "Actuarial Science"
        profile.gpa = "3.50"
        profile.preferred_employment_type = "internship"
        profile.preferred_work_arrangement = "hybrid"
        profile.target_job_level = "internship"
        profile.resume.save("resume.pdf", SimpleUploadedFile("resume.pdf", b"%PDF-1.4", content_type="application/pdf"))
        profile.save()
        area = PracticeArea.objects.create(name="Life")
        profile.preferred_practice_areas.add(area)
        UserExam.objects.create(user=self.user, exam=self.exam, status="planned")
        UserSkill.objects.create(user=self.user, skill=self.skill, proficiency_level="intermediate")
        WorkExperience.objects.create(user=self.user, company="Insurer", job_title="Intern", start_date=date(2026, 1, 1))

        result = calculate_profile_completeness(self.user)

        self.assertEqual(result.percentage, 100)
        self.assertEqual(result.missing_sections, ())


class ReferenceDataCommandTests(TestCase):
    def test_seeded_exams_skills_and_practice_areas_are_idempotent(self):
        call_command("seed_reference_data", verbosity=0)
        first_counts = (ActuarialExam.objects.count(), Skill.objects.count(), PracticeArea.objects.count())
        call_command("seed_reference_data", verbosity=0)

        self.assertEqual(first_counts, (14, 14, 10))
        self.assertEqual(
            (ActuarialExam.objects.count(), Skill.objects.count(), PracticeArea.objects.count()),
            first_counts,
        )

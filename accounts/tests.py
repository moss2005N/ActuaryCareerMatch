from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class AuthenticationTests(TestCase):
    def test_registration_creates_and_logs_in_user(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "newcandidate",
                "email": "candidate@example.com",
                "password1": "A-strong-test-password-2026",
                "password2": "A-strong-test-password-2026",
            },
        )

        self.assertRedirects(response, reverse("profiles:detail"))
        self.assertTrue(User.objects.filter(username="newcandidate").exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), User.objects.get().pk)

    def test_login(self):
        user = User.objects.create_user(username="candidate", password="test-password-2026")

        response = self.client.post(
            reverse("accounts:login"),
            {"username": user.username, "password": "test-password-2026"},
        )

        self.assertRedirects(response, reverse("profiles:detail"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_logout(self):
        user = User.objects.create_user(username="candidate", password="test-password-2026")
        self.client.force_login(user)

        response = self.client.post(reverse("accounts:logout"))

        self.assertRedirects(response, reverse("core:home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_new_user_automatically_receives_profile(self):
        user = User.objects.create_user(username="candidate")

        self.assertTrue(hasattr(user, "candidate_profile"))


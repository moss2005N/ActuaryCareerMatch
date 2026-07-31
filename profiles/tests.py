from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class ProfilePermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="test-password-2026")
        self.other_user = User.objects.create_user(username="other")

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


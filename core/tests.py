from django.test import TestCase
from django.urls import reverse


class HomeViewTests(TestCase):
    def test_homepage_responds_successfully(self):
        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Find the actuarial opportunity")


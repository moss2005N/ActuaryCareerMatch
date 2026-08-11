import re
from datetime import timedelta
from urllib.parse import urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import PhoneNumberForm
from .models import EmailVerificationToken, PhoneOTPChallenge, SecurityAttempt
from .security import (
    OTPThrottled,
    generate_recovery_codes,
    issue_phone_otp,
    make_email_verification_token,
    verify_phone_otp,
)

User = get_user_model()
PASSWORD = "A-strong-test-password-2026"


@override_settings(
    DEBUG=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PHONE_VERIFICATION_BACKEND="console",
    OTP_RESEND_COOLDOWN_SECONDS=0,
)
class AccountSecurityTests(TestCase):
    def create_user(self, username="candidate", email="candidate@example.com", **kwargs):
        defaults = {
            "password": PASSWORD,
            "email_verified": True,
            "email_verified_at": timezone.now(),
            "phone_number": "+12025550123",
            "phone_number_verified": True,
            "phone_number_verified_at": timezone.now(),
        }
        defaults.update(kwargs)
        return User.objects.create_user(username=username, email=email, **defaults)

    def set_session_value(self, key, value):
        session = self.client.session
        session[key] = value
        session.save()

    def test_registration_sends_verification_email_without_authenticating(self):
        response = self.client.post(reverse("accounts:register"), {
            "username": "newcandidate",
            "email": "candidate@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("_auth_user_id", self.client.session)
        user = User.objects.get(username="newcandidate")
        self.assertFalse(user.email_verified)
        self.assertTrue(hasattr(user, "candidate_profile"))

    def test_fresh_registration_verification_link_from_email_is_valid(self):
        self.client.post(reverse("accounts:register"), {
            "username": "freshcandidate",
            "email": "fresh@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
        })
        verification_url = re.search(r"https?://[^\s]+", mail.outbox[0].body).group(0)

        response = self.client.get(urlsplit(verification_url).path)

        self.assertRedirects(response, reverse("accounts:phone_change"))
        user = User.objects.get(username="freshcandidate")
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(user.email_verified_at)
        self.assertEqual(self.client.session["security_setup_user_id"], user.pk)

    def test_fresh_registration_link_as_emitted_by_console_is_valid(self):
        self.client.post(reverse("accounts:register"), {
            "username": "consolecandidate",
            "email": "console@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
        })
        console_message = mail.outbox[0].message().as_string()
        emitted_url = re.search(r"https?://[^\s]+", console_message).group(0)

        response = self.client.get(urlsplit(emitted_url).path, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.resolver_match.url_name, "phone_change")

    def test_unverified_email_cannot_complete_login(self):
        self.create_user(email_verified=False, email_verified_at=None)

        response = self.client.post(reverse("accounts:login"), {
            "identifier": "candidate@example.com",
            "password": PASSWORD,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Verify your email")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_valid_email_verification_succeeds(self):
        user = self.create_user(email_verified=False, email_verified_at=None, phone_number=None, phone_number_verified=False)
        token = make_email_verification_token(user)

        response = self.client.get(reverse("accounts:verify_email", args=[token]))

        self.assertRedirects(response, reverse("accounts:phone_change"))
        user.refresh_from_db()
        self.assertTrue(user.email_verified)

    def test_reusing_verification_link_fails_safely(self):
        user = self.create_user(
            email_verified=False,
            email_verified_at=None,
            phone_number=None,
            phone_number_verified=False,
        )
        token = make_email_verification_token(user)
        path = reverse("accounts:verify_email", args=[token])

        self.assertEqual(self.client.get(path).status_code, 302)
        response = self.client.get(path)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "invalid or expired", status_code=400)

    def test_invalid_email_verification_fails_safely(self):
        response = self.client.get(reverse("accounts:verify_email", args=["invalid-token"]))

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "invalid or expired", status_code=400)

    @override_settings(EMAIL_VERIFICATION_TIMEOUT_SECONDS=10)
    def test_expired_email_verification_fails_safely(self):
        user = self.create_user(email_verified=False, email_verified_at=None)
        token = make_email_verification_token(user)
        EmailVerificationToken.objects.update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        response = self.client.get(reverse("accounts:verify_email", args=[token]))

        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)

    def test_verification_link_cannot_verify_another_user(self):
        owner = self.create_user(
            email_verified=False,
            email_verified_at=None,
            phone_number=None,
            phone_number_verified=False,
        )
        other = self.create_user(
            username="other",
            email="other@example.com",
            email_verified=False,
            email_verified_at=None,
            phone_number="+12025550124",
            phone_number_verified=False,
        )
        token = make_email_verification_token(owner)

        response = self.client.get(reverse("accounts:verify_email", args=[token]))

        self.assertRedirects(response, reverse("accounts:phone_change"))
        owner.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(owner.email_verified)
        self.assertFalse(other.email_verified)

    def test_email_uniqueness_is_case_insensitive(self):
        self.create_user(email="Candidate@Example.com")

        response = self.client.post(reverse("accounts:register"), {
            "username": "another",
            "email": "CANDIDATE@example.COM",
            "password1": PASSWORD,
            "password2": PASSWORD,
        })

        self.assertContains(response, "cannot be used")
        self.assertEqual(User.objects.count(), 1)

    def test_database_enforces_case_insensitive_email_uniqueness(self):
        self.create_user(email="candidate@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="another", email="CANDIDATE@EXAMPLE.COM", password=PASSWORD)

    def test_phone_normalization_and_uniqueness(self):
        owner = self.create_user()
        form = PhoneNumberForm({"phone_number": "+1 (202) 555-0123"}, user=owner)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["phone_number"], "+12025550123")

        other = self.create_user(username="other", email="other@example.com", phone_number="+12025550124")
        duplicate = PhoneNumberForm({"phone_number": "+1 202 555 0123"}, user=other)
        self.assertFalse(duplicate.is_valid())

    @patch("accounts.security.secrets.randbelow", return_value=123456)
    def test_valid_phone_otp_succeeds_and_is_single_use(self, _random):
        user = self.create_user(phone_number_verified=False)
        issue_phone_otp(user, PhoneOTPChallenge.Purpose.PHONE_VERIFICATION)

        self.assertTrue(verify_phone_otp(user, PhoneOTPChallenge.Purpose.PHONE_VERIFICATION, "123456", self._request()))
        self.assertFalse(verify_phone_otp(user, PhoneOTPChallenge.Purpose.PHONE_VERIFICATION, "123456", self._request()))

    @patch("accounts.security.secrets.randbelow", return_value=123456)
    def test_invalid_phone_otp_fails(self, _random):
        user = self.create_user()
        issue_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN)
        self.assertFalse(verify_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN, "000000", self._request()))

    @patch("accounts.security.secrets.randbelow", return_value=123456)
    def test_expired_phone_otp_fails(self, _random):
        user = self.create_user()
        challenge = issue_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN)
        challenge.expires_at = timezone.now() - timedelta(seconds=1)
        challenge.save(update_fields=["expires_at"])
        self.assertFalse(verify_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN, "123456", self._request()))

    @patch("accounts.security.secrets.randbelow", side_effect=[111111, 222222])
    def test_superseded_phone_otp_fails(self, _random):
        user = self.create_user()
        first = issue_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN)
        issue_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN)
        first.refresh_from_db()
        self.assertIsNotNone(first.used_at)
        self.assertFalse(verify_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN, "111111", self._request()))
        self.assertTrue(verify_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN, "222222", self._request()))

    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=60)
    @patch("accounts.security.secrets.randbelow", return_value=123456)
    def test_resend_throttling(self, _random):
        user = self.create_user()
        issue_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN)
        with self.assertRaises(OTPThrottled):
            issue_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN)

    @override_settings(OTP_MAX_ATTEMPTS_PER_ACCOUNT_IP_PER_HOUR=2)
    @patch("accounts.security.secrets.randbelow", return_value=123456)
    def test_attempt_throttling(self, _random):
        user = self.create_user()
        issue_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN)
        request = self._request()
        self.assertFalse(verify_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN, "000000", request))
        self.assertFalse(verify_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN, "000001", request))
        with self.assertRaises(OTPThrottled):
            verify_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN, "123456", request)

    @patch("accounts.security.secrets.randbelow", return_value=123456)
    def test_login_does_not_authenticate_before_phone_otp(self, _random):
        self.create_user()
        response = self.client.post(reverse("accounts:login"), {
            "identifier": "CANDIDATE@EXAMPLE.COM",
            "password": PASSWORD,
        })
        self.assertRedirects(response, reverse("accounts:login_otp"))
        self.assertNotIn("_auth_user_id", self.client.session)

    @patch("accounts.security.secrets.randbelow", return_value=123456)
    def test_successful_otp_creates_authenticated_session(self, _random):
        user = self.create_user()
        self.client.post(reverse("accounts:login"), {"identifier": user.username, "password": PASSWORD})

        response = self.client.post(reverse("accounts:login_otp"), {"code": "123456"})

        self.assertRedirects(response, reverse("profiles:detail"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_recovery_code_works_only_once(self):
        user = self.create_user()
        raw_code = generate_recovery_codes(user, count=1)[0]
        self.set_session_value("pending_login_user_id", user.pk)

        response = self.client.post(reverse("accounts:recovery_login"), {"recovery_code": raw_code})
        self.assertRedirects(response, reverse("accounts:security"))
        self.client.post(reverse("accounts:logout"))
        self.client.post(reverse("accounts:login"), {
            "identifier": user.email,
            "password": PASSWORD,
        })

        response = self.client.post(reverse("accounts:recovery_login"), {"recovery_code": raw_code})
        self.assertContains(response, "already been used")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_changing_email_requires_reverification(self):
        user = self.create_user()
        self.client.force_login(user)

        response = self.client.post(reverse("accounts:change_email"), {"email": "new@example.com"})

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")
        self.assertFalse(user.email_verified)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(len(mail.outbox), 1)

    @patch("accounts.security.secrets.randbelow", return_value=123456)
    def test_changing_phone_requires_password_and_reverification(self, _random):
        user = self.create_user()
        self.client.force_login(user)

        bad = self.client.post(reverse("accounts:phone_change"), {
            "phone_number": "+12025550199",
            "password": "wrong",
        })
        self.assertContains(bad, "could not be confirmed")
        user.refresh_from_db()
        self.assertEqual(user.phone_number, "+12025550123")

        response = self.client.post(reverse("accounts:phone_change"), {
            "phone_number": "+12025550199",
            "password": PASSWORD,
        })
        self.assertRedirects(response, reverse("accounts:phone_verify"))
        user.refresh_from_db()
        self.assertFalse(user.phone_number_verified)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_users_cannot_access_another_users_security_flow(self):
        owner = self.create_user()
        other = self.create_user(username="other", email="other@example.com", phone_number="+12025550124")
        self.client.force_login(owner)

        response = self.client.get(reverse("accounts:security"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["user"], owner)
        self.assertNotContains(response, other.email)
        self.assertNotContains(response, other.phone_number)

    @override_settings(DEBUG=True)
    def test_staff_and_superusers_are_not_locked_out_locally(self):
        staff = User.objects.create_superuser("admin", "admin@example.com", PASSWORD)

        response = self.client.post(reverse("accounts:login"), {
            "identifier": staff.email,
            "password": PASSWORD,
        })

        self.assertRedirects(response, reverse("profiles:detail"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), staff.pk)

    def _request(self):
        from django.test import RequestFactory
        return RequestFactory().post("/", REMOTE_ADDR="203.0.113.10")

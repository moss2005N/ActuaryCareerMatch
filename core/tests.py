import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import TestCase
from django.urls import reverse


class HomeViewTests(TestCase):
    def test_homepage_responds_successfully(self):
        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Find the actuarial opportunity")


class ProductionSettingsTests(TestCase):
    settings_keys = {
        "DJANGO_ENVIRONMENT", "DEBUG", "SECRET_KEY", "ALLOWED_HOSTS",
        "CSRF_TRUSTED_ORIGINS", "DB_ENGINE", "SQLITE_NAME", "DB_NAME",
        "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "EMAIL_BACKEND",
        "DEFAULT_FROM_EMAIL", "EMAIL_HOST", "PHONE_VERIFICATION_BACKEND",
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_VERIFY_SERVICE_SID",
        "SECURE_SSL_REDIRECT", "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE",
        "SECURE_HSTS_SECONDS", "SECURE_HSTS_INCLUDE_SUBDOMAINS",
        "SECURE_HSTS_PRELOAD", "TRUST_X_FORWARDED_PROTO",
    }

    def import_settings(self, **values):
        environment = os.environ.copy()
        for key in self.settings_keys:
            environment.pop(key, None)
        environment.update(values)
        code = (
            "import json; import config.settings as s; "
            "print(json.dumps({"
            "'debug': s.DEBUG, 'hosts': s.ALLOWED_HOSTS, "
            "'ssl': s.SECURE_SSL_REDIRECT, "
            "'session': s.SESSION_COOKIE_SECURE, "
            "'csrf': s.CSRF_COOKIE_SECURE, "
            "'hsts': s.SECURE_HSTS_SECONDS, "
            "'proxy': getattr(s, 'SECURE_PROXY_SSL_HEADER', None)"
            "}))"
        )
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parent.parent,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def secure_production_values(self):
        return {
            "DJANGO_ENVIRONMENT": "production",
            "DEBUG": "False",
            "SECRET_KEY": "Audit-only-9x!Strong-Production-Key-Placeholder-7v@2026-Long",
            "ALLOWED_HOSTS": "app.example.com",
            "CSRF_TRUSTED_ORIGINS": "https://app.example.com",
            "DB_ENGINE": "sqlite",
            "SQLITE_NAME": "settings-test.sqlite3",
            "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "DEFAULT_FROM_EMAIL": "Actuary Career Match <noreply@example.com>",
            "EMAIL_HOST": "smtp.example.com",
            "PHONE_VERIFICATION_BACKEND": "twilio",
            "TWILIO_ACCOUNT_SID": "test-account-placeholder",
            "TWILIO_AUTH_TOKEN": "test-token-placeholder",
            "TWILIO_VERIFY_SERVICE_SID": "test-service-placeholder",
        }

    def test_production_requires_a_strong_secret_key(self):
        values = self.secure_production_values()
        values.pop("SECRET_KEY")

        result = self.import_settings(**values)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("strong SECRET_KEY", result.stderr)

    def test_secure_production_configuration_and_explicit_proxy_trust(self):
        values = self.secure_production_values()
        values.update({
            "SECURE_HSTS_SECONDS": "31536000",
            "TRUST_X_FORWARDED_PROTO": "True",
        })

        result = self.import_settings(**values)

        self.assertEqual(result.returncode, 0, result.stderr)
        loaded = json.loads(result.stdout)
        self.assertFalse(loaded["debug"])
        self.assertEqual(loaded["hosts"], ["app.example.com"])
        self.assertTrue(loaded["ssl"])
        self.assertTrue(loaded["session"])
        self.assertTrue(loaded["csrf"])
        self.assertEqual(loaded["hsts"], 31536000)
        self.assertEqual(loaded["proxy"], ["HTTP_X_FORWARDED_PROTO", "https"])

    def test_forwarded_proto_is_not_trusted_by_default(self):
        result = self.import_settings(**self.secure_production_values())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(json.loads(result.stdout)["proxy"])

    def test_production_rejects_debug_wildcard_hosts_and_console_services(self):
        invalid_sets = (
            {"DEBUG": "True"},
            {"ALLOWED_HOSTS": "*"},
            {"EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend"},
            {"PHONE_VERIFICATION_BACKEND": "console"},
        )
        for invalid in invalid_sets:
            with self.subTest(invalid=invalid):
                values = self.secure_production_values()
                values.update(invalid)
                result = self.import_settings(**values)
                self.assertNotEqual(result.returncode, 0)

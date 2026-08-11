from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class ConsolePhoneBackend:
    name = "console"
    manages_codes = False

    def send(self, phone_number, purpose, code):
        if settings.DEBUG:
            print(f"[Actuary Career Match] Phone verification code for {phone_number}: {code}")
        return ""

    def check(self, phone_number, code):
        raise NotImplementedError


class TwilioVerifyBackend:
    name = "twilio"
    manages_codes = True

    def __init__(self):
        try:
            from twilio.rest import Client
        except ImportError as exc:
            raise ImproperlyConfigured(
                "Install the optional 'twilio' package to use the Twilio backend."
            ) from exc
        required = (
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
            settings.TWILIO_VERIFY_SERVICE_SID,
        )
        if not all(required):
            raise ImproperlyConfigured("Twilio Verify environment variables are incomplete.")
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.service_sid = settings.TWILIO_VERIFY_SERVICE_SID

    def send(self, phone_number, purpose, code=None):
        verification = self.client.verify.v2.services(self.service_sid).verifications.create(
            to=phone_number,
            channel="sms",
        )
        return verification.sid

    def check(self, phone_number, code):
        check = self.client.verify.v2.services(self.service_sid).verification_checks.create(
            to=phone_number,
            code=code,
        )
        return check.status == "approved"


def get_phone_backend(name=None):
    backend_name = (name or settings.PHONE_VERIFICATION_BACKEND).lower()
    if backend_name == "console":
        return ConsolePhoneBackend()
    if backend_name == "twilio":
        return TwilioVerifyBackend()
    raise ImproperlyConfigured(f"Unknown phone verification backend: {backend_name}")

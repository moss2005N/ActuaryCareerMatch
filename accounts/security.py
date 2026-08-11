import hashlib
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import EmailVerificationToken, PhoneOTPChallenge, RecoveryCode, SecurityAttempt
from .phone_backends import get_phone_backend

E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


class OTPError(Exception):
    pass


class OTPThrottled(OTPError):
    pass


def normalize_phone_number(value):
    value = re.sub(r"[\s().-]", "", (value or "").strip())
    if not E164_PATTERN.fullmatch(value):
        raise ValidationError("Enter a phone number in E.164 format, such as +12025550123.")
    return value


def make_email_verification_token(user):
    raw_token = secrets.token_urlsafe(16)
    now = timezone.now()
    EmailVerificationToken.objects.filter(
        user=user,
        used_at__isnull=True,
    ).update(used_at=now)
    EmailVerificationToken.objects.create(
        user=user,
        email=user.email,
        token_digest=hashlib.sha256(raw_token.encode()).hexdigest(),
        expires_at=now + timedelta(seconds=settings.EMAIL_VERIFICATION_TIMEOUT_SECONDS),
    )
    return raw_token


def read_email_verification_token(token):
    if not token or len(token) > 128:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    return EmailVerificationToken.objects.filter(token_digest=digest).select_related("user").first()


def hash_ip(request):
    value = request.META.get("REMOTE_ADDR", "")
    return hashlib.sha256(f"{settings.SECRET_KEY}:{value}".encode()).hexdigest()


def mask_email(email):
    local, separator, domain = email.partition("@")
    if not separator:
        return "••••"
    visible = local[:1]
    return f"{visible}{'•' * max(3, len(local) - 1)}@{domain}"


def mask_phone(phone):
    return f"••••••••{phone[-4:]}" if phone else "Not added"


def issue_phone_otp(user, purpose):
    if not user.phone_number:
        raise OTPError("A phone number is required.")

    now = timezone.now()
    recent = PhoneOTPChallenge.objects.filter(
        phone_number=user.phone_number,
        sent_at__gte=now - timedelta(hours=1),
    )
    latest = recent.order_by("-sent_at").first()
    if latest and latest.sent_at > now - timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS):
        raise OTPThrottled("Please wait before requesting another code.")
    if recent.count() >= settings.OTP_MAX_SENDS_PER_PHONE_PER_HOUR:
        raise OTPThrottled("Too many codes requested. Please try again later.")

    backend = get_phone_backend()
    raw_code = None
    with transaction.atomic():
        PhoneOTPChallenge.objects.select_for_update().filter(
            user=user,
            purpose=purpose,
            used_at__isnull=True,
        ).update(used_at=now)
        challenge = PhoneOTPChallenge(
            user=user,
            phone_number=user.phone_number,
            purpose=purpose,
            backend=backend.name,
            expires_at=now + timedelta(seconds=settings.OTP_EXPIRY_SECONDS),
        )
        if backend.manages_codes:
            challenge.code_hash = make_password(None)
            challenge.save()
            challenge.provider_reference = backend.send(user.phone_number, purpose)
            challenge.save(update_fields=["provider_reference"])
        else:
            raw_code = f"{secrets.randbelow(1_000_000):06d}"
            challenge.set_code(raw_code)
            challenge.save()
            backend.send(user.phone_number, purpose, raw_code)
    return challenge


def _attempt_is_throttled(user, request):
    since = timezone.now() - timedelta(hours=1)
    return SecurityAttempt.objects.filter(
        user=user,
        ip_hash=hash_ip(request),
        created_at__gte=since,
    ).count() >= settings.OTP_MAX_ATTEMPTS_PER_ACCOUNT_IP_PER_HOUR


def verify_phone_otp(user, purpose, raw_code, request):
    if _attempt_is_throttled(user, request):
        raise OTPThrottled("Too many attempts. Please try again later.")

    SecurityAttempt.objects.create(user=user, ip_hash=hash_ip(request))
    challenge = PhoneOTPChallenge.objects.filter(
        user=user,
        purpose=purpose,
        used_at__isnull=True,
    ).order_by("-created_at").first()
    if not challenge or not challenge.is_active or challenge.phone_number != user.phone_number:
        return False
    if challenge.attempts >= settings.OTP_MAX_ATTEMPTS_PER_CHALLENGE:
        return False

    challenge.attempts += 1
    challenge.save(update_fields=["attempts"])
    backend = get_phone_backend(challenge.backend)
    is_valid = (
        backend.check(challenge.phone_number, raw_code)
        if backend.manages_codes
        else challenge.matches(raw_code)
    )
    if not is_valid:
        return False

    challenge.used_at = timezone.now()
    challenge.save(update_fields=["used_at"])
    return True


def generate_recovery_codes(user, count=8):
    raw_codes = [f"{secrets.token_hex(4).upper()}-{secrets.token_hex(2).upper()}" for _ in range(count)]
    with transaction.atomic():
        user.recovery_codes.filter(used_at__isnull=True).update(used_at=timezone.now())
        for raw_code in raw_codes:
            code = RecoveryCode(user=user)
            code.set_code(raw_code)
            code.save()
    return raw_codes


def consume_recovery_code(user, raw_code):
    for code in user.recovery_codes.filter(used_at__isnull=True):
        if code.matches(raw_code.strip().upper()):
            code.used_at = timezone.now()
            code.save(update_fields=["used_at"])
            return True
    return False

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class UserManager(DjangoUserManager):
    def _create_user(self, username, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        return super()._create_user(username, email.strip().lower(), password, **extra_fields)


class User(AbstractUser):
    email = models.EmailField("email address", unique=True)
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(blank=True, null=True)
    phone_number = models.CharField(max_length=16, unique=True, blank=True, null=True)
    phone_number_verified = models.BooleanField(default=False)
    phone_number_verified_at = models.DateTimeField(blank=True, null=True)

    REQUIRED_FIELDS = ["email"]
    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        if not self.phone_number:
            self.phone_number = None
        super().save(*args, **kwargs)


class PhoneOTPChallenge(models.Model):
    class Purpose(models.TextChoices):
        PHONE_VERIFICATION = "phone_verification", "Phone verification"
        LOGIN = "login", "Login"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="phone_otp_challenges")
    phone_number = models.CharField(max_length=16)
    purpose = models.CharField(max_length=24, choices=Purpose.choices)
    code_hash = models.CharField(max_length=128)
    backend = models.CharField(max_length=32, default="console")
    provider_reference = models.CharField(max_length=100, blank=True)
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField(default=timezone.now)
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "purpose", "created_at"]),
            models.Index(fields=["phone_number", "created_at"]),
        ]

    @property
    def is_active(self):
        return self.used_at is None and self.expires_at > timezone.now()

    def set_code(self, raw_code):
        self.code_hash = make_password(raw_code)

    def matches(self, raw_code):
        return check_password(raw_code, self.code_hash)


class EmailVerificationToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verification_tokens",
    )
    email = models.EmailField()
    token_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "email", "created_at"])]


class SecurityAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="security_attempts")
    ip_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "ip_hash", "created_at"])]


class RecoveryCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(blank=True, null=True)

    def set_code(self, raw_code):
        self.code_hash = make_password(raw_code)

    def matches(self, raw_code):
        return check_password(raw_code, self.code_hash)

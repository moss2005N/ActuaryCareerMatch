from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    ChangeEmailForm,
    OTPForm,
    PasswordConfirmationForm,
    PhoneNumberForm,
    RecoveryCodeForm,
    RegistrationForm,
    TwoStepLoginForm,
)
from .models import EmailVerificationToken, PhoneOTPChallenge, User
from .security import (
    OTPThrottled,
    consume_recovery_code,
    generate_recovery_codes,
    issue_phone_otp,
    make_email_verification_token,
    mask_email,
    mask_phone,
    read_email_verification_token,
    verify_phone_otp,
)

PENDING_LOGIN_KEY = "pending_login_user_id"
PENDING_LOGIN_NEXT_KEY = "pending_login_next"
SECURITY_SETUP_KEY = "security_setup_user_id"


def _safe_next_url(request):
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return ""


def _set_pending_login_destination(request, destination):
    if destination:
        request.session[PENDING_LOGIN_NEXT_KEY] = destination
    else:
        request.session.pop(PENDING_LOGIN_NEXT_KEY, None)


def _consume_login_destination(request):
    destination = request.session.pop(PENDING_LOGIN_NEXT_KEY, "")
    return destination or reverse("profiles:detail")


def _send_verification_email(request, user):
    token = make_email_verification_token(user)
    verification_url = request.build_absolute_uri(
        reverse("accounts:verify_email", kwargs={"token": token})
    )
    message = EmailMessage(
        subject="Verify your Actuary Career Match email",
        body=(
            f"Verify your email address by opening this link:\n\n{verification_url}\n\n"
            "If you did not create or update this account, ignore this message."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    # The body and signed URL are ASCII. Keeping the local console message 7-bit
    # prevents quoted-printable soft breaks from being copied into the token.
    message.encoding = "us-ascii"
    message.send(fail_silently=False)


def _pending_user(request, key):
    user_id = request.session.get(key)
    if not user_id:
        raise Http404
    return get_object_or_404(User, pk=user_id, is_active=True)


def register(request):
    if request.user.is_authenticated:
        return redirect("profiles:detail")
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email_verified = False
            user.save()
            _send_verification_email(request, user)
            request.session[SECURITY_SETUP_KEY] = user.pk
            return render(
                request,
                "accounts/email_verification_sent.html",
                {"masked_email": mask_email(user.email)},
            )
    else:
        form = RegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


def verify_email(request, token):
    token_record = read_email_verification_token(token)
    if token_record is None:
        return render(request, "accounts/email_verification_invalid.html", status=400)
    with transaction.atomic():
        token_record = EmailVerificationToken.objects.select_for_update().select_related("user").get(
            pk=token_record.pk
        )
        user = token_record.user
        now = timezone.now()
        if (
            token_record.used_at is not None
            or token_record.expires_at <= now
            or user.email.lower() != token_record.email.lower()
            or user.email_verified
        ):
            return render(request, "accounts/email_verification_invalid.html", status=400)
        user.email_verified = True
        user.email_verified_at = now
        user.save(update_fields=["email_verified", "email_verified_at"])
        token_record.used_at = now
        token_record.save(update_fields=["used_at"])
    request.session[SECURITY_SETUP_KEY] = user.pk
    if user.phone_number_verified:
        return redirect("accounts:login")
    return redirect("accounts:phone_change")


def login_step_one(request):
    if request.user.is_authenticated:
        return redirect("profiles:detail")
    form = TwoStepLoginForm(request.POST or None, request=request)
    safe_next = _safe_next_url(request)
    if request.method == "POST" and form.is_valid():
        user = form.user
        if settings.DEBUG and (user.is_staff or user.is_superuser):
            login(request, user)
            return redirect("profiles:detail")
        if not user.email_verified:
            _send_verification_email(request, user)
            return render(request, "accounts/email_verification_required.html")
        if not user.phone_number_verified or not user.phone_number:
            request.session[SECURITY_SETUP_KEY] = user.pk
            return redirect("accounts:phone_change")
        request.session[PENDING_LOGIN_KEY] = user.pk
        _set_pending_login_destination(request, safe_next)
        try:
            issue_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN)
        except OTPThrottled as exc:
            form.add_error(None, str(exc))
        else:
            return redirect("accounts:login_otp")
    return render(request, "accounts/login.html", {"form": form, "next": safe_next})


def login_otp(request):
    user = _pending_user(request, PENDING_LOGIN_KEY)
    form = OTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            valid = verify_phone_otp(
                user,
                PhoneOTPChallenge.Purpose.LOGIN,
                form.cleaned_data["code"],
                request,
            )
        except OTPThrottled as exc:
            form.add_error(None, str(exc))
        else:
            if valid:
                destination = _consume_login_destination(request)
                request.session.pop(PENDING_LOGIN_KEY, None)
                login(request, user)
                return redirect(destination)
            form.add_error("code", "The code is invalid or has expired.")
    return render(
        request,
        "accounts/otp_form.html",
        {
            "form": form,
            "purpose": "Complete sign in",
            "masked_phone": mask_phone(user.phone_number),
            "resend_url": reverse("accounts:resend_login_otp"),
            "recovery_url": reverse("accounts:recovery_login"),
        },
    )


@require_POST
def resend_login_otp(request):
    user = _pending_user(request, PENDING_LOGIN_KEY)
    try:
        issue_phone_otp(user, PhoneOTPChallenge.Purpose.LOGIN)
        messages.success(request, "A new code was sent.")
    except OTPThrottled as exc:
        messages.error(request, str(exc))
    return redirect("accounts:login_otp")


def phone_change(request):
    if request.user.is_authenticated:
        user = request.user
        require_password = True
    else:
        user = _pending_user(request, SECURITY_SETUP_KEY)
        require_password = False
        if not user.email_verified:
            raise Http404

    form = PhoneNumberForm(
        request.POST or None,
        user=user,
        require_password=require_password,
    )
    if request.method == "POST" and form.is_valid():
        user.phone_number = form.cleaned_data["phone_number"]
        user.phone_number_verified = False
        user.phone_number_verified_at = None
        user.save(
            update_fields=[
                "phone_number",
                "phone_number_verified",
                "phone_number_verified_at",
            ]
        )
        if request.user.is_authenticated:
            logout(request)
            request.session[SECURITY_SETUP_KEY] = user.pk
        try:
            issue_phone_otp(user, PhoneOTPChallenge.Purpose.PHONE_VERIFICATION)
        except OTPThrottled as exc:
            form.add_error(None, str(exc))
        else:
            return redirect("accounts:phone_verify")
    return render(request, "accounts/phone_form.html", {"form": form})


def phone_verify(request):
    user = _pending_user(request, SECURITY_SETUP_KEY)
    form = OTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            valid = verify_phone_otp(
                user,
                PhoneOTPChallenge.Purpose.PHONE_VERIFICATION,
                form.cleaned_data["code"],
                request,
            )
        except OTPThrottled as exc:
            form.add_error(None, str(exc))
        else:
            if valid:
                user.phone_number_verified = True
                user.phone_number_verified_at = timezone.now()
                user.save(update_fields=["phone_number_verified", "phone_number_verified_at"])
                request.session.pop(SECURITY_SETUP_KEY, None)
                codes = generate_recovery_codes(user)
                login(request, user)
                return render(request, "accounts/recovery_codes_created.html", {"codes": codes})
            form.add_error("code", "The code is invalid or has expired.")
    return render(
        request,
        "accounts/otp_form.html",
        {
            "form": form,
            "purpose": "Verify your phone",
            "masked_phone": mask_phone(user.phone_number),
            "resend_url": reverse("accounts:resend_phone_otp"),
        },
    )


@require_POST
def resend_phone_otp(request):
    user = _pending_user(request, SECURITY_SETUP_KEY)
    try:
        issue_phone_otp(user, PhoneOTPChallenge.Purpose.PHONE_VERIFICATION)
        messages.success(request, "A new code was sent.")
    except OTPThrottled as exc:
        messages.error(request, str(exc))
    return redirect("accounts:phone_verify")


def recovery_login(request):
    user = _pending_user(request, PENDING_LOGIN_KEY)
    form = RecoveryCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if consume_recovery_code(user, form.cleaned_data["recovery_code"]):
            destination = _consume_login_destination(request)
            request.session.pop(PENDING_LOGIN_KEY, None)
            login(request, user)
            return redirect(destination)
        form.add_error("recovery_code", "The recovery code is invalid or has already been used.")
    return render(request, "accounts/recovery_login.html", {"form": form})


@login_required
def security(request):
    return render(
        request,
        "accounts/security.html",
        {
            "masked_email": mask_email(request.user.email),
            "masked_phone": mask_phone(request.user.phone_number),
        },
    )


@login_required
def change_email(request):
    form = ChangeEmailForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        user = request.user
        user.email = form.cleaned_data["email"]
        user.email_verified = False
        user.email_verified_at = None
        user.save(update_fields=["email", "email_verified", "email_verified_at"])
        _send_verification_email(request, user)
        logout(request)
        request.session[SECURITY_SETUP_KEY] = user.pk
        return render(
            request,
            "accounts/email_verification_sent.html",
            {"masked_email": mask_email(user.email)},
        )
    return render(request, "accounts/change_email.html", {"form": form})


@login_required
def regenerate_recovery_codes(request):
    form = PasswordConfirmationForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        codes = generate_recovery_codes(request.user)
        return render(request, "accounts/recovery_codes_created.html", {"codes": codes})
    return render(request, "accounts/regenerate_recovery_codes.html", {"form": form})

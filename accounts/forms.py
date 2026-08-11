from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm

from .models import User
from .security import normalize_phone_number


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email address cannot be used.")
        return email


class TwoStepLoginForm(forms.Form):
    identifier = forms.CharField(label="Username or email")
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user = None

    def clean(self):
        cleaned = super().clean()
        identifier = cleaned.get("identifier")
        password = cleaned.get("password")
        if identifier and password:
            self.user = authenticate(self.request, username=identifier, password=password)
            if self.user is None:
                raise forms.ValidationError("The credentials could not be verified.")
        return cleaned


class PhoneNumberForm(forms.Form):
    phone_number = forms.CharField(
        help_text="Use E.164 format, including country code (for example, +12025550123)."
    )

    def __init__(self, *args, user=None, require_password=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if require_password:
            self.fields["password"] = forms.CharField(
                label="Confirm your password",
                widget=forms.PasswordInput,
            )

    def clean_phone_number(self):
        phone = normalize_phone_number(self.cleaned_data["phone_number"])
        if User.objects.filter(phone_number=phone).exclude(pk=getattr(self.user, "pk", None)).exists():
            raise forms.ValidationError("This phone number cannot be used.")
        return phone

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("The password could not be confirmed.")
        return password


class OTPForm(forms.Form):
    code = forms.RegexField(
        regex=r"^\d{6}$",
        max_length=6,
        label="Six-digit code",
        error_messages={"invalid": "Enter a valid six-digit code."},
    )


class RecoveryCodeForm(forms.Form):
    recovery_code = forms.CharField(max_length=20)


class ChangeEmailForm(forms.Form):
    email = forms.EmailField()

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("This email address cannot be used.")
        return email


class PasswordConfirmationForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("The password could not be confirmed.")
        return password

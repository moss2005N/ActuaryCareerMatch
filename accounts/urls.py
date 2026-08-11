from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("verify-email/<str:token>/", views.verify_email, name="verify_email"),
    path("login/", views.login_step_one, name="login"),
    path("login/code/", views.login_otp, name="login_otp"),
    path("login/code/resend/", views.resend_login_otp, name="resend_login_otp"),
    path("login/recovery/", views.recovery_login, name="recovery_login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("security/", views.security, name="security"),
    path("security/email/", views.change_email, name="change_email"),
    path("security/phone/", views.phone_change, name="phone_change"),
    path("security/phone/verify/", views.phone_verify, name="phone_verify"),
    path("security/phone/resend/", views.resend_phone_otp, name="resend_phone_otp"),
    path(
        "security/recovery-codes/",
        views.regenerate_recovery_codes,
        name="regenerate_recovery_codes",
    ),
]

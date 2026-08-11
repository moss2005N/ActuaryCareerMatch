from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone

from .models import PhoneOTPChallenge, RecoveryCode, SecurityAttempt, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Verification", {"fields": (
            "email_verified", "email_verified_at", "phone_number",
            "phone_number_verified", "phone_number_verified_at",
        )}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Contact", {"fields": ("email", "phone_number")}),
    )
    list_display = UserAdmin.list_display + ("email_verified", "phone_number_verified")
    list_filter = UserAdmin.list_filter + ("email_verified", "phone_number_verified")
    search_fields = UserAdmin.search_fields + ("phone_number",)
    readonly_fields = ("email_verified_at", "phone_number_verified_at")
    actions = ("mark_email_verified_for_development", "mark_phone_verified_for_development")

    @admin.action(description="DEV recovery: mark email verified")
    def mark_email_verified_for_development(self, request, queryset):
        if not settings.DEBUG:
            self.message_user(request, "This recovery action is disabled outside DEBUG.", messages.ERROR)
            return
        queryset.update(email_verified=True, email_verified_at=timezone.now())

    @admin.action(description="DEV recovery: mark existing phone verified")
    def mark_phone_verified_for_development(self, request, queryset):
        if not settings.DEBUG:
            self.message_user(request, "This recovery action is disabled outside DEBUG.", messages.ERROR)
            return
        queryset.exclude(phone_number__isnull=True).update(
            phone_number_verified=True,
            phone_number_verified_at=timezone.now(),
        )


@admin.register(PhoneOTPChallenge)
class PhoneOTPChallengeAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "masked_phone", "backend", "sent_at", "expires_at", "used_at")
    list_filter = ("purpose", "backend", "used_at")
    search_fields = ("user__username", "user__email", "phone_number")
    readonly_fields = [field.name for field in PhoneOTPChallenge._meta.fields]

    @admin.display(description="Phone")
    def masked_phone(self, obj):
        return f"••••{obj.phone_number[-4:]}"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RecoveryCode)
class RecoveryCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "used_at")
    readonly_fields = [field.name for field in RecoveryCode._meta.fields]
    exclude = ("code_hash",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SecurityAttempt)
class SecurityAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")
    readonly_fields = [field.name for field in SecurityAttempt._meta.fields]
    exclude = ("ip_hash",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

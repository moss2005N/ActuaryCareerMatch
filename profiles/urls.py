from django.urls import path

from .views import profile_detail, profile_edit

app_name = "profiles"

urlpatterns = [
    path("", profile_detail, name="detail"),
    path("edit/", profile_edit, name="edit"),
]


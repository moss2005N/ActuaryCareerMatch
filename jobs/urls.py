from django.urls import path

from .views import JobDetailView, JobListView

app_name = "jobs"

urlpatterns = [
    path("", JobListView.as_view(), name="list"),
    path("<int:pk>/", JobDetailView.as_view(), name="detail"),
]


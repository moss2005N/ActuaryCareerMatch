from django.urls import path

from .views import JobDetailView, JobListView, RecommendedJobsView, refresh_match_explanation

app_name = "jobs"

urlpatterns = [
    path("", JobListView.as_view(), name="list"),
    path("recommended/", RecommendedJobsView.as_view(), name="recommended"),
    path("<int:pk>/explanation/", refresh_match_explanation, name="refresh_explanation"),
    path("<int:pk>/", JobDetailView.as_view(), name="detail"),
]

from django.urls import path

from .views import (
    JobDetailView, JobListView, MyJobsView, RecommendedJobsView, application_edit,
    mark_as_applied, refresh_match_explanation, save_job, start_tracking, unsave_job,
)

app_name = "jobs"

urlpatterns = [
    path("", JobListView.as_view(), name="list"),
    path("recommended/", RecommendedJobsView.as_view(), name="recommended"),
    path("my-jobs/", MyJobsView.as_view(), name="my_jobs"),
    path("applications/<int:pk>/", application_edit, name="application_edit"),
    path("<int:pk>/save/", save_job, name="save"),
    path("<int:pk>/unsave/", unsave_job, name="unsave"),
    path("<int:pk>/track/", start_tracking, name="start_tracking"),
    path("<int:pk>/mark-applied/", mark_as_applied, name="mark_applied"),
    path("<int:pk>/explanation/", refresh_match_explanation, name="refresh_explanation"),
    path("<int:pk>/", JobDetailView.as_view(), name="detail"),
]

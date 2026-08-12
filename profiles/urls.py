from django.urls import path

from . import views

app_name = "profiles"

urlpatterns = [
    path("", views.profile_detail, name="detail"),
    path("edit/", views.profile_edit, name="edit"),
    path("exams/", views.exams, name="exams"),
    path("exams/<int:pk>/edit/", views.exam_edit, name="exam_edit"),
    path("skills/", views.skills, name="skills"),
    path("skills/<int:pk>/edit/", views.skill_edit, name="skill_edit"),
    path("education/", views.education, name="education"),
    path("education/<int:pk>/edit/", views.education_edit, name="education_edit"),
    path("experience/", views.experience, name="experience"),
    path("experience/<int:pk>/edit/", views.experience_edit, name="experience_edit"),
    path("resume/", views.resume, name="resume"),
    path("resume/download/", views.resume_download, name="resume_download"),
    path("resume/delete/", views.resume_delete, name="resume_delete"),
    path("<str:kind>/<int:pk>/delete/", views.record_delete, name="record_delete"),
]

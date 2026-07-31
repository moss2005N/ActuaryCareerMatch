from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import CandidateProfileForm


@login_required
def profile_detail(request):
    return render(
        request,
        "profiles/profile_detail.html",
        {"profile": request.user.candidate_profile},
    )


@login_required
def profile_edit(request):
    profile = request.user.candidate_profile
    if request.method == "POST":
        form = CandidateProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("profiles:detail")
    else:
        form = CandidateProfileForm(instance=profile)

    return render(request, "profiles/profile_form.html", {"form": form})


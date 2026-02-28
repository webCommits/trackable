from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from trackable.profiles.forms import ProfileForm
from trackable.profiles.models import Profile


@login_required
def profile_list(request):
    profiles = request.user.profiles.all()
    return render(request, "profiles/list.html", {"profiles": profiles})


@login_required
def profile_create(request):
    if request.method == "POST":
        form = ProfileForm(request.POST)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            messages.success(request, _('Profile "%(title)s" was created successfully!') % {"title": profile.title})
            return redirect("profile_detail", pk=profile.pk)
    else:
        form = ProfileForm()
    return render(request, "profiles/create.html", {"form": form})


@login_required
def profile_detail(request, pk):
    profile = get_object_or_404(Profile, pk=pk, user=request.user)

    from datetime import datetime

    current_date = timezone.now().date()

    # Collect all (year, month) tuples that actually have entries,
    # plus always include the current month.
    entry_months = set(
        profile.time_entries.values_list("date__year", "date__month").distinct()
    )
    entry_months.add((current_date.year, current_date.month))

    months = []
    for year, month in sorted(entry_months, reverse=True):
        hours = profile.get_monthly_hours(year, month)
        months.append({
            "year": year,
            "month": month,
            "month_name": datetime(year, month, 1).strftime("%B %Y"),
            "hours": hours,
            "earnings": profile.get_monthly_earnings(year, month),
        })

    return render(request, "profiles/detail.html", {"profile": profile, "months": months})


@login_required
def profile_edit(request, pk):
    profile = get_object_or_404(Profile, pk=pk, user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, _("Profile was updated successfully!"))
            return redirect("profile_detail", pk=profile.pk)
    else:
        form = ProfileForm(instance=profile)
    return render(request, "profiles/create.html", {"form": form, "edit": True, "profile": profile})


@login_required
def profile_delete(request, pk):
    profile = get_object_or_404(Profile, pk=pk, user=request.user)
    if request.method == "POST":
        profile.delete()
        messages.success(request, _("Profile was deleted."))
        return redirect("profile_list")
    return redirect("profile_detail", pk=pk)

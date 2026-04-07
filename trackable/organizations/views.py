from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from trackable.organizations.models import Organization, OrganizationMembership
from trackable.organizations.forms import (
    OrganizationForm,
    EmployeeCreateForm,
    HolidayForm,
)
from trackable.organizations.decorators import org_manager_required
from trackable.profiles.models import Profile
from trackable.core.models import Holiday
from trackable.accounts.models import User
from datetime import datetime


@login_required
def org_dashboard(request):
    membership = getattr(request.user, "organization_membership", None)
    if not membership:
        return redirect("org_create")

    organization = membership.organization
    if not membership.is_manager:
        return render(
            request,
            "organizations/employee_dashboard.html",
            {"organization": organization, "membership": membership},
        )

    memberships = organization.memberships.select_related("user").all()
    employee_memberships = [m for m in memberships if m.role == "employee"]
    manager_memberships = [m for m in memberships if m.role == "manager"]

    return render(
        request,
        "organizations/dashboard.html",
        {
            "organization": organization,
            "employee_memberships": employee_memberships,
            "manager_memberships": manager_memberships,
            "total_employees": len(employee_memberships),
        },
    )


@login_required
def org_create(request):
    if hasattr(request.user, "organization_membership"):
        messages.info(request, _("You are already part of an organization."))
        return redirect("org_dashboard")

    if request.method == "POST":
        form = OrganizationForm(request.POST)
        if form.is_valid():
            organization = form.save(commit=False)
            organization.created_by = request.user
            organization.save()
            OrganizationMembership.objects.create(
                organization=organization,
                user=request.user,
                role="manager",
            )
            messages.success(
                request,
                _('Organization "%(name)s" created successfully!')
                % {"name": organization.name},
            )
            return redirect("org_dashboard")
    else:
        form = OrganizationForm()

    return render(request, "organizations/create.html", {"form": form})


@login_required
@org_manager_required
def employee_create(request):
    membership = request.user.organization_membership
    organization = membership.organization

    if request.method == "POST":
        form = EmployeeCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            OrganizationMembership.objects.create(
                organization=organization,
                user=user,
                role="employee",
            )
            messages.success(
                request,
                _('Employee "%(name)s" created successfully!')
                % {"name": user.get_full_name() or user.username},
            )
            return redirect("org_dashboard")
    else:
        form = EmployeeCreateForm()

    return render(
        request,
        "organizations/employee_create.html",
        {"form": form, "organization": organization},
    )


@login_required
@org_manager_required
def employee_detail(request, user_id):
    membership = request.user.organization_membership
    organization = membership.organization

    employee_membership = get_object_or_404(
        OrganizationMembership,
        organization=organization,
        user_id=user_id,
    )
    employee = employee_membership.user

    profiles = employee.profiles.all()

    current_date = datetime.now().date()
    profile_data = []
    for profile in profiles:
        entry_months = set(
            profile.time_entries.values_list("date__year", "date__month").distinct()
        )
        entry_months.add((current_date.year, current_date.month))

        months = []
        for year, month in sorted(entry_months, reverse=True):
            hours = profile.get_monthly_hours(year, month)
            months.append(
                {
                    "year": year,
                    "month": month,
                    "month_name": datetime(year, month, 1).strftime("%B %Y"),
                    "hours": hours,
                    "earnings": profile.get_monthly_earnings(year, month),
                }
            )

        profile_data.append({"profile": profile, "months": months})

    return render(
        request,
        "organizations/employee_detail.html",
        {
            "organization": organization,
            "employee": employee,
            "employee_membership": employee_membership,
            "profile_data": profile_data,
        },
    )


@login_required
@org_manager_required
def employee_profile_detail(request, user_id, profile_id):
    membership = request.user.organization_membership
    organization = membership.organization

    employee_membership = get_object_or_404(
        OrganizationMembership,
        organization=organization,
        user_id=user_id,
    )
    employee = employee_membership.user

    profile = get_object_or_404(Profile, pk=profile_id, user=employee)

    import calendar
    from django.utils import timezone

    year = int(request.GET.get("year", timezone.now().year))
    month = int(request.GET.get("month", timezone.now().month))

    time_entries = list(profile.get_monthly_entries(year, month).order_by("date"))
    last_day = calendar.monthrange(year, month)[1]
    from trackable.timetracking.models import VacationEntry

    vacation_entries = list(
        profile.vacation_entries.filter(
            start_date__lte=datetime(year, month, last_day).date(),
            end_date__gte=datetime(year, month, 1).date(),
        ).order_by("start_date")
    )
    total_hours = profile.get_monthly_hours(year, month)
    total_earnings = profile.get_monthly_earnings(year, month)
    total_vacation_days = sum(v.workdays for v in vacation_entries)
    month_name = datetime(year, month, 1).strftime("%B %Y")

    entry_months = set(
        profile.time_entries.values_list("date__year", "date__month").distinct()
    )
    entry_months.add((timezone.now().year, timezone.now().month))
    available_months = sorted(entry_months, reverse=True)

    return render(
        request,
        "organizations/employee_profile_detail.html",
        {
            "organization": organization,
            "employee": employee,
            "profile": profile,
            "time_entries": time_entries,
            "vacation_entries": vacation_entries,
            "year": year,
            "month": month,
            "month_name": month_name,
            "total_hours": total_hours,
            "total_earnings": total_earnings,
            "total_vacation_days": total_vacation_days,
            "available_months": available_months,
        },
    )


@login_required
@org_manager_required
def employee_remove(request, user_id):
    membership = request.user.organization_membership
    organization = membership.organization

    employee_membership = get_object_or_404(
        OrganizationMembership,
        organization=organization,
        user_id=user_id,
    )
    employee = employee_membership.user

    if request.method == "POST":
        employee_membership.delete()
        messages.success(
            request,
            _("%(name)s has been removed from the organization.")
            % {"name": employee.get_full_name() or employee.username},
        )
        return redirect("org_dashboard")

    return render(
        request,
        "organizations/employee_remove.html",
        {"organization": organization, "employee": employee},
    )


@login_required
@org_manager_required
def holiday_list(request):
    membership = request.user.organization_membership
    organization = membership.organization
    from django.utils import timezone

    current_year = timezone.now().year
    year = int(request.GET.get("year", current_year))
    holidays = organization.holidays.filter(date__year=year).order_by("date")
    year_range = range(current_year - 1, current_year + 3)
    return render(
        request,
        "organizations/holiday_list.html",
        {
            "organization": organization,
            "holidays": holidays,
            "year": year,
            "year_range": year_range,
        },
    )


@login_required
@org_manager_required
def holiday_create(request):
    membership = request.user.organization_membership
    organization = membership.organization

    if request.method == "POST":
        form = HolidayForm(request.POST)
        if form.is_valid():
            holiday = form.save(commit=False)
            holiday.organization = organization
            holiday.save()
            messages.success(
                request,
                _('Holiday "%(name)s" added successfully!') % {"name": holiday.name},
            )
            return redirect("org_holidays")
    else:
        form = HolidayForm()

    return render(
        request,
        "organizations/holiday_form.html",
        {"form": form, "organization": organization},
    )


@login_required
@org_manager_required
def holiday_delete(request, pk):
    membership = request.user.organization_membership
    organization = membership.organization

    holiday = get_object_or_404(Holiday, pk=pk, organization=organization)
    if request.method == "POST":
        holiday.delete()
        messages.success(request, _("Holiday deleted."))
    return redirect("org_holidays")

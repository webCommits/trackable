from django.shortcuts import redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from functools import wraps


def org_manager_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        membership = getattr(request.user, "organization_membership", None)
        if membership and membership.is_manager:
            return view_func(request, *args, **kwargs)
        messages.error(request, _("You do not have permission to access this page."))
        return redirect("home")

    return wrapper

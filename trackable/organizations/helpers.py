def can_edit_time_entries(user):
    """Check if a user can manually create/edit/delete time entries.

    - Without org membership: always allowed
    - Org mode 'classic': always allowed
    - Org mode 'restricted': only managers/owners allowed
    """
    membership = getattr(user, "organization_membership", None)
    if not membership:
        return True
    org = membership.organization
    if org.time_tracking_mode == "classic":
        return True
    # restricted mode
    return membership.is_manager


def is_org_manager(user):
    """Return True if the user is a manager in their organization."""
    membership = getattr(user, "organization_membership", None)
    return membership is not None and membership.is_manager


def get_user_organization(user):
    """Return the organization of a user, or None."""
    membership = getattr(user, "organization_membership", None)
    return membership.organization if membership else None


def can_manage_profile_time_entries(user, profile):
    """Check if a user can add/edit/delete time entries for a profile via form.

    - Owner of the profile: allowed if can_edit_time_entries(user)
    - Manager of the same organization: always allowed (bypasses restricted mode)
    """
    if profile.user == user:
        return can_edit_time_entries(user)

    if not is_org_manager(user):
        return False

    user_org = get_user_organization(user)
    profile_org = get_user_organization(profile.user)

    return user_org is not None and user_org == profile_org


def can_manage_time_entry(user, entry):
    """Check if a user can edit/delete a specific time entry via form."""
    return can_manage_profile_time_entries(user, entry.profile)


def can_modify_entry(user, entry):
    """Check if a user can modify (edit/move/delete) a specific time entry
    in the weekly calendar (shared planning view).

    - Managers can modify any entry in their organization.
    - Employees can only modify their own entries.
    - Returns False if the user has no org membership or the entry belongs
      to a different organization.
    """
    membership = getattr(user, "organization_membership", None)
    if not membership:
        return False

    # Check entry belongs to the same org
    entry_membership = getattr(entry.profile.user, "organization_membership", None)
    if not entry_membership or entry_membership.organization != membership.organization:
        return False

    if membership.is_manager:
        return True

    # Employee: only their own entry
    if entry.profile.user == user:
        return True

    return False


def can_create_calendar_entry(user, profile):
    """Check if a user can create a time entry in the weekly calendar.

    - Managers can create entries for any employee.
    - Employees can create entries only for themselves.
    - Always allowed for org members (bypasses restricted timer mode).
    """
    membership = getattr(user, "organization_membership", None)
    if not membership:
        return False

    if membership.is_manager:
        return True

    if profile.user == user:
        return True

    return False

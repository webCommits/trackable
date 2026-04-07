from django.contrib import admin
from trackable.organizations.models import Organization, OrganizationMembership
from trackable.core.admin_site import custom_admin_site


@admin.register(Organization, site=custom_admin_site)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "created_by", "created_at"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(OrganizationMembership, site=custom_admin_site)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "role", "joined_at"]
    list_filter = ["role", "organization"]
    search_fields = ["user__username", "user__email"]

from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from trackable.core.admin_site import custom_admin_site


def health_check(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("admin/", custom_admin_site.urls),
    path("accounts/", include("trackable.accounts.urls")),
    path("", include("trackable.timetracking.urls")),
    path("profiles/", include("trackable.profiles.urls")),
    path("org/", include("trackable.organizations.urls")),
    path("", include("trackable.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

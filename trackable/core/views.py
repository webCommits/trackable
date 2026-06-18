from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils import translation


def landing(request):
    return render(request, "core/landing.html")


def impressum(request):
    return render(request, "core/impressum.html")


def datenschutz(request):
    return render(request, "core/datenschutz.html")


def set_language(request):
    next_url = request.META.get("HTTP_REFERER", "/")
    lang_code = request.POST.get("language", settings.LANGUAGE_CODE)
    if lang_code in dict(settings.LANGUAGES):
        translation.activate(lang_code)
        response = HttpResponseRedirect(next_url)
        response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang_code)
        return response
    return HttpResponseRedirect(next_url)

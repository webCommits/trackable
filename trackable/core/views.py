from django.shortcuts import render


def landing(request):
    return render(request, "core/landing.html")


def impressum(request):
    return render(request, "core/impressum.html")


def datenschutz(request):
    return render(request, "core/datenschutz.html")

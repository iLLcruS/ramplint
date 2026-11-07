"""A pretend login: any name logs you in. Good enough to try scans behind login."""

from django.conf import settings
from django.shortcuts import redirect, render, resolve_url
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import LoginForm, ProfileForm

SESSION_KEY = "demo_user"


def login(request):
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        request.session[SESSION_KEY] = form.cleaned_data["username"]
        target = request.GET.get("next", "")
        if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
            target = resolve_url("accounts:profile")
        return redirect(target)
    return render(request, "accounts/login.html", {"form": form})


def logout(request):
    request.session.flush()
    return redirect("catalog:list")


def profile(request):
    if SESSION_KEY not in request.session:
        return redirect(f"{resolve_url(settings.LOGIN_URL)}?next={request.path}")
    return render(request, "accounts/profile.html", {"form": ProfileForm()})

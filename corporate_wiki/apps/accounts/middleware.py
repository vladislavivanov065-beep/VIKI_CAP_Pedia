from __future__ import annotations

from django.shortcuts import redirect
from django.urls import reverse

# Paths an authenticated user with must_change_password=True is still
# allowed to reach. Static files never hit this middleware — WhiteNoise
# intercepts them earlier in the chain.
_ALLOWED_URL_NAMES = {"accounts:password_change", "accounts:logout"}


class ForcePasswordChangeMiddleware:
    """Confine users with a pending mandatory password change.

    Runs after LoginRequiredMiddleware, so by the time this executes any
    anonymous request has already been redirected to the login page.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._allowed_paths = None

    def _allowed_paths_set(self) -> set[str]:
        if self._allowed_paths is None:
            self._allowed_paths = {reverse(name) for name in _ALLOWED_URL_NAMES}
        return self._allowed_paths

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and getattr(user, "must_change_password", False)
            and request.path not in self._allowed_paths_set()
        ):
            return redirect("accounts:password_change")
        return self.get_response(request)

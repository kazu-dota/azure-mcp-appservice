from urllib.parse import urlencode

import httpx
import pytest

from scripts.smoke import verify_login_redirect


@pytest.mark.parametrize("authority", ["login.microsoftonline.com", "unexpected.example"])
def test_browser_probe_requires_the_expected_entra_authority(authority):
    frontend = "https://demo.azurewebsites.net"
    data = {"tenant_id": "tenant", "frontend_login_id": "client"}

    def respond(request):
        if request.headers.get("accept") != "text/html":
            return httpx.Response(401)
        query = urlencode(
            {"client_id": "client", "redirect_uri": frontend + "/.auth/login/aad/callback"}
        )
        return httpx.Response(
            302,
            headers={"location": f"https://{authority}/tenant/oauth2/v2.0/authorize?{query}"},
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        if authority == "login.microsoftonline.com":
            verify_login_redirect(http, frontend, data)
        else:
            with pytest.raises(AssertionError, match="authority"):
                verify_login_redirect(http, frontend, data)

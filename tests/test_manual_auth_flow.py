import unittest

from custom_components.bwt_best_water_home.auth_flow import (
    AuthRedirectError,
    build_authorization_url,
    build_refresh_token_form,
    build_token_exchange_form,
    create_bwt_manual_auth_session,
    extract_access_token,
    extract_authorization_code,
    extract_token_data,
)
from custom_components.bwt_best_water_home.const import (
    BWT_AUTHORIZATION_URL,
    BWT_CLIENT_ID,
    BWT_REDIRECT_URI,
    BWT_SCOPE,
    BWT_TOKEN_URL,
)


class ManualAuthFlowTests(unittest.TestCase):
    def test_build_authorization_url_uses_exact_redirect_and_pkce_challenge(self):
        url = build_authorization_url(
            authorize_url="https://login.example.test/oauth/authorize",
            client_id="mobile-client",
            redirect_uri="com.bwt.athomeapp://login/",
            state="state-123",
            code_challenge="challenge-abc",
            scope="openid profile offline_access",
        )

        self.assertIn("https://login.example.test/oauth/authorize?", url)
        self.assertIn("client_id=mobile-client", url)
        self.assertIn("redirect_uri=com.bwt.athomeapp%3A%2F%2Flogin%2F", url)
        self.assertIn("response_type=code", url)
        self.assertIn("state=state-123", url)
        self.assertIn("code_challenge=challenge-abc", url)
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("scope=openid+profile+offline_access", url)

    def test_extract_authorization_code_accepts_full_redirect_url(self):
        code = extract_authorization_code(
            "com.bwt.athomeapp://login/?code=code-123&state=state-123",
            expected_state="state-123",
        )

        self.assertEqual(code, "code-123")

    def test_extract_authorization_code_accepts_raw_code(self):
        code = extract_authorization_code("code-123", expected_state="state-123")

        self.assertEqual(code, "code-123")

    def test_extract_authorization_code_rejects_state_mismatch(self):
        with self.assertRaises(AuthRedirectError):
            extract_authorization_code(
                "com.bwt.athomeapp://login/?code=code-123&state=wrong",
                expected_state="state-123",
            )

    def test_extract_authorization_code_rejects_oauth_error_redirect(self):
        with self.assertRaises(AuthRedirectError):
            extract_authorization_code(
                "com.bwt.athomeapp://login/?error=access_denied&error_description=Denied&state=state-123",
                expected_state="state-123",
            )

    def test_bwt_manual_auth_session_uses_confirmed_app_oauth_values(self):
        session = create_bwt_manual_auth_session()

        self.assertTrue(session.authorization_url.startswith(BWT_AUTHORIZATION_URL + "?"))
        self.assertIn(f"client_id={BWT_CLIENT_ID}", session.authorization_url)
        self.assertIn("redirect_uri=com.bwt.home.app%3A%2F%2Fsignin", session.authorization_url)
        self.assertIn("scope=openid+profile+offline_access+email+aidu-api", session.authorization_url)
        self.assertEqual(BWT_REDIRECT_URI, "com.bwt.home.app://signin")
        self.assertEqual(BWT_TOKEN_URL, "https://account.bwt-group.com/connect/token")
        self.assertEqual(BWT_SCOPE, "openid profile offline_access email aidu-api")

    def test_build_bwt_token_exchange_form_uses_confirmed_app_oauth_values(self):
        form = build_token_exchange_form(
            client_id=BWT_CLIENT_ID,
            redirect_uri=BWT_REDIRECT_URI,
            code="code-123",
            code_verifier="verifier-123",
        )

        self.assertEqual(form["grant_type"], "authorization_code")
        self.assertEqual(form["client_id"], "bwt-best-water-app-prod")
        self.assertEqual(form["redirect_uri"], "com.bwt.home.app://signin")
        self.assertEqual(form["code"], "code-123")
        self.assertEqual(form["code_verifier"], "verifier-123")

    def test_extract_token_data_preserves_refresh_token_and_expiry(self):
        token_data = extract_token_data({
            "access_token": " access-123 ",
            "refresh_token": " refresh-123 ",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "openid profile offline_access email aidu-api",
        })

        self.assertEqual(token_data["access_token"], "access-123")
        self.assertEqual(token_data["refresh_token"], "refresh-123")
        self.assertEqual(token_data["expires_in"], 3600)
        self.assertEqual(token_data["token_type"], "Bearer")
        self.assertEqual(token_data["scope"], "openid profile offline_access email aidu-api")
        self.assertIn("expires_at", token_data)

    def test_extract_access_token_still_returns_access_token(self):
        self.assertEqual(extract_access_token({"access_token": " access-123 "}), "access-123")

    def test_build_refresh_token_form_uses_bwt_client(self):
        form = build_refresh_token_form(client_id=BWT_CLIENT_ID, refresh_token="refresh-123")

        self.assertEqual(form["grant_type"], "refresh_token")
        self.assertEqual(form["client_id"], "bwt-best-water-app-prod")
        self.assertEqual(form["refresh_token"], "refresh-123")


if __name__ == "__main__":
    unittest.main()

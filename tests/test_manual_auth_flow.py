import unittest

from custom_components.bwt_best_water_home.auth_flow import (
    AuthRedirectError,
    build_authorization_url,
    extract_authorization_code,
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


if __name__ == "__main__":
    unittest.main()

"""Re-auth detection — automatically detect login pages, CAPTCHA, and MFA challenges."""

from __future__ import annotations

import logging
import re
from typing import Any

from playwright.async_api import Page

logger = logging.getLogger("browser_runtime.reauth")


class ReauthDetector:
    """Detects authentication challenges and emits structured events.

    Categories:
    - login_form: Standard username/password form detected
    - captcha: CAPTCHA challenge (reCAPTCHA, hCaptcha, etc.)
    - mfa: Multi-factor authentication (2FA code prompt)
    - sso: SSO redirect / OAuth consent
    - session_expired: Session timeout page
    - blocked: IP block / rate limit page
    """

    # Known indicators per category
    _LOGIN_KEYWORDS = re.compile(
        r"(sign.in|log.in|login|signin|log_in|credentials|username|password|"
        r"continue.with|authenticate|welcome.back)", re.IGNORECASE
    )
    _CAPTCHA_KEYWORDS = re.compile(
        r"(captcha|recaptcha|hcaptcha|turnstile|i.am.not.a.robot|"
        r"verify.you.are.human|security.check)", re.IGNORECASE
    )
    _MFA_KEYWORDS = re.compile(
        r"(two.factor|2fa|2.fa|multi.factor|mfa|verification.code|"
        r"authenticator.code|otp|one.time.pass|security.code|"
        r"enter.the.code|check.your.email|check.your.phone)", re.IGNORECASE
    )

    @staticmethod
    async def detect(page: Page, url: str | None = None) -> dict[str, Any]:
        """Check the current page for auth challenges. Returns detection results."""
        result: dict[str, Any] = {"auth_detected": False, "challenges": []}

        try:
            page_url = url or page.url
            content_lower = (await page.content()).lower()
            title = (await page.title()).lower()

            checks = [
                ("login_form", ReauthDetector._LOGIN_KEYWORDS, 0.7),
                ("captcha", ReauthDetector._CAPTCHA_KEYWORDS, 0.9),
                ("mfa", ReauthDetector._MFA_KEYWORDS, 0.85),
            ]

            for challenge_name, pattern, threshold in checks:
                if pattern.search(content_lower) or pattern.search(title):
                    confidence = ReauthDetector._estimate_confidence(page, challenge_name)
                    if confidence >= threshold:
                        result["challenges"].append({
                            "type": challenge_name,
                            "confidence": confidence,
                            "url": page_url,
                        })
                        result["auth_detected"] = True

            # URL-based detection for common auth pages
            url_lower = page_url.lower()
            if any(p in url_lower for p in ["/login", "/signin", "/auth", "/oauth",
                                              "/saml", "/sso", "/2fa", "/mfa"]):
                if not any(c["type"] == "login_form" for c in result["challenges"]):
                    result["challenges"].append({
                        "type": "login_form",
                        "confidence": 0.6,
                        "url": page_url,
                        "detected_by": "url_pattern",
                    })
                    result["auth_detected"] = True

            result["challenge_count"] = len(result["challenges"])
            return result
        except Exception as exc:
            return {"auth_detected": False, "challenges": [], "error": str(exc)}

    @staticmethod
    async def _estimate_confidence(page: Page, challenge_type: str) -> float:
        """Estimate confidence based on visible elements."""
        try:
            if challenge_type == "captcha":
                has_iframe = await page.evaluate(
                    "document.querySelector('iframe[src*=recaptcha], iframe[src*=hcaptcha], "
                    "div[class*=captcha], div[id*=captcha]') !== null"
                )
                return 0.95 if has_iframe else 0.7
            if challenge_type == "login_form":
                has_password = await page.evaluate(
                    "document.querySelector('input[type=password]') !== null"
                )
                return 0.9 if has_password else 0.6
            if challenge_type == "mfa":
                has_code_input = await page.evaluate(
                    "document.querySelector('input[inputmode=numeric], "
                    "input[autocomplete=one-time-code]') !== null"
                )
                return 0.95 if has_code_input else 0.7
        except Exception:
            pass
        return 0.5


class CaptchaMFAHandler:
    """Handles CAPTCHA and MFA challenges by emitting human handoff requests."""

    @staticmethod
    async def request_human_handoff(page: Page, challenge: dict[str, Any]) -> dict[str, Any]:
        """Emit a human handoff request for CAPTCHA or MFA challenges."""
        challenge_type = challenge.get("type", "unknown")
        url = challenge.get("url", page.url)

        handoff = {
            "handoff_required": True,
            "challenge_type": challenge_type,
            "url": url,
            "message": f"Human handoff required: {challenge_type} detected at {url}",
            "instructions": CaptchaMFAHandler._instructions(challenge_type),
        }
        logger.warning("Human handoff requested: %s at %s", challenge_type, url)
        return handoff

    @staticmethod
    def _instructions(challenge_type: str) -> str:
        if challenge_type == "captcha":
            return ("CAPTCHA detected. Please solve the CAPTCHA manually. "
                    "KIO will resume automation after completion.")
        if challenge_type == "mfa":
            return ("MFA/2FA code required. Please enter the verification code. "
                    "KIO will resume automation after authentication.")
        if challenge_type == "login_form":
            return ("Login form detected. Please enter your credentials. "
                    "Session will be saved for future use.")
        return f"Authentication challenge '{challenge_type}' requires manual intervention."

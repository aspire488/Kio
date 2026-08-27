"""Focused test: gateway waits for cooldown recovery instead of failing
instantly when the chain is empty (the live 429-burst failure)."""
import asyncio
import time

from mini_kio.llm.llm_gateway import LLMGateway
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus
from mini_kio.llm.provider_base import LLMProvider
from mini_kio.llm.provider_registry import ProviderFailoverRegistry, ProviderState


class _StubProvider(LLMProvider):
    def __init__(self, name: str):
        self._name = name
        self._ok = False

    @property
    def provider_name(self) -> str:
        return self._name

    async def health_check(self) -> bool:
        return True

    def set_ok(self, ok: bool):
        self._ok = ok

    async def generate(self, request):
        if not self._ok:
            return LLMResponse(
                success=False, status=LLMStatus.ERROR,
                content="", error_code="GROQ_RATE_LIMITED", provider=self.provider_name,
            )
        return LLMResponse(
            success=True, status=LLMStatus.SUCCESS,
            content="hello from stub", provider=self.provider_name,
        )


def test_empty_chain_waits_for_recovery():
    gw = LLMGateway()
    p = _StubProvider("stub")
    gw.register_provider(p, priority=0)

    # Simulate the post-burst state: provider in cooldown expiring in ~1.5s.
    reg: ProviderFailoverRegistry = gw.get_registry()
    reg._states["stub"] = ProviderState.COOLDOWN
    reg._cooldown_until["stub"] = time.time() + 1.5
    assert reg.get_chain() == []  # chain empty right now
    p.set_ok(True)  # after recovery the provider works

    t0 = time.monotonic()
    resp = asyncio.run(gw.generate(LLMRequest(prompt="hi", max_tokens=50)))
    elapsed = time.monotonic() - t0
    assert resp.success, f"expected recovery, got {resp.error_code}"
    assert resp.content == "hello from stub"
    assert elapsed >= 1.2, f"should have waited for cooldown, took {elapsed:.2f}s"


def test_empty_chain_long_cooldown_still_fails_bounded():
    gw = LLMGateway()
    p = _StubProvider("stub2")
    gw.register_provider(p, priority=0)
    reg: ProviderFailoverRegistry = gw.get_registry()
    reg._states["stub2"] = ProviderState.COOLDOWN
    reg._cooldown_until["stub2"] = time.time() + 300.0  # long cooldown

    t0 = time.monotonic()
    resp = asyncio.run(gw.generate(LLMRequest(prompt="hi", max_tokens=50)))
    elapsed = time.monotonic() - t0
    assert not resp.success
    # Must NOT hang for 300s; bounded by the recovery-wait cap (~12s).
    assert elapsed < 20, f"should be bounded, took {elapsed:.2f}s"


def test_retry_pass_waits_for_recovery():
    """First pass hits rate limits on a provider with a short cooldown; the
    bounded retry pass must recover instead of returning the fallback."""
    gw = LLMGateway()
    gw._TRANSIENT_RETRY_SLEEP_S = 0.1
    gw._TRANSIENT_RETRY_MAX_S = 8.0

    class _Flaky(LLMProvider):
        _name = "flaky"
        _attempts = 0

        @property
        def provider_name(self) -> str:
            return self._name

        async def health_check(self) -> bool:
            return True

        async def generate(self, request):
            _Flaky._attempts += 1
            if _Flaky._attempts <= 1:
                # First attempt rate-limits and (threshold=1) enters cooldown.
                return LLMResponse(
                    success=False, status=LLMStatus.ERROR,
                    content="", error_code="RATE_LIMITED", provider=self.provider_name,
                )
            return LLMResponse(
                success=True, status=LLMStatus.SUCCESS,
                content="recovered", provider=self.provider_name,
            )

    gw.register_provider(_Flaky(), priority=0)
    reg: ProviderFailoverRegistry = gw.get_registry()
    reg.COOLDOWN_THRESHOLD = 1  # first failure -> cooldown
    reg.COOLDOWN_RATE_LIMIT_S = 1  # short cooldown

    resp = asyncio.run(gw.generate(LLMRequest(prompt="hi", max_tokens=50)))
    assert resp.success, f"expected retry-pass recovery, got {resp.error_code}"
    assert resp.content == "recovered"


if __name__ == "__main__":
    test_empty_chain_waits_for_recovery()
    print("ok: empty chain waits for recovery")
    test_empty_chain_long_cooldown_still_fails_bounded()
    print("ok: long cooldown bounded")
    test_retry_pass_waits_for_recovery()
    print("ok: retry pass recovers")

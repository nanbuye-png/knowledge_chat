"""Tests for Sprint 28 Step 3: API Rate Limiting.

Run: cd backend && ..\\.venv\\Scripts\\python.exe -m pytest tests/test_rate_limit.py -v
"""

import sys
import time
from unittest.mock import patch

sys.path.insert(0, ".")

import pytest


# ============================================================================
# Test 1 — RateLimiter core logic
# ============================================================================


class TestMemoryRateLimiter:
    """Test the MemoryRateLimiter core logic."""

    def test_normal_request_succeeds(self):
        """First request within limit should return True."""
        from app.services.security.rate_limiter import MemoryRateLimiter

        limiter = MemoryRateLimiter()
        result = limiter.check("test-key", limit=5, window_seconds=60)
        assert result is True

    def test_within_limit_allows_requests(self):
        """Multiple requests within limit should all succeed."""
        from app.services.security.rate_limiter import MemoryRateLimiter

        limiter = MemoryRateLimiter()
        for _ in range(3):
            result = limiter.check("test-key-2", limit=3, window_seconds=60)
            assert result is True

        # 4th request should be blocked
        result = limiter.check("test-key-2", limit=3, window_seconds=60)
        assert result is False

    def test_exceeding_limit_returns_false(self):
        """When limit is exceeded, check returns False."""
        from app.services.security.rate_limiter import MemoryRateLimiter

        limiter = MemoryRateLimiter()
        key = "exceed-test"

        # Fill up to limit
        for _ in range(2):
            assert limiter.check(key, limit=2, window_seconds=60)

        # 3rd attempt blocked
        assert limiter.check(key, limit=2, window_seconds=60) is False

    def test_different_keys_counted_independently(self):
        """Different keys should have independent counters."""
        from app.services.security.rate_limiter import MemoryRateLimiter

        limiter = MemoryRateLimiter()

        # Exhaust key-A
        for _ in range(2):
            limiter.check("key-A", limit=2, window_seconds=60)
        assert limiter.check("key-A", limit=2, window_seconds=60) is False

        # key-B should still be allowed (unaffected)
        assert limiter.check("key-B", limit=2, window_seconds=60) is True

    def test_window_expiry_allows_new_requests(self):
        """After window expires, requests should be allowed again."""
        from app.services.security.rate_limiter import MemoryRateLimiter

        limiter = MemoryRateLimiter()
        key = "window-expiry-test"

        with patch("app.services.security.rate_limiter.time") as mock_time:
            # Fill limit at t=0
            mock_time.time.return_value = 0.0
            for _ in range(2):
                limiter.check(key, limit=2, window_seconds=60)
            # Blocked at t=0
            assert limiter.check(key, limit=2, window_seconds=60) is False

            # Fast-forward 61 seconds — window should be expired
            mock_time.time.return_value = 61.0
            assert limiter.check(key, limit=2, window_seconds=60) is True

    def test_clear_removes_all_keys(self):
        """clear() should reset all tracked keys."""
        from app.services.security.rate_limiter import MemoryRateLimiter

        limiter = MemoryRateLimiter()
        for _ in range(3):
            limiter.check("k1", limit=3, window_seconds=60)
        assert limiter.check("k1", limit=3, window_seconds=60) is False

        limiter.clear()
        assert limiter.check("k1", limit=3, window_seconds=60) is True

    def test_clear_specific_key(self):
        """clear('key') should only remove that key."""
        from app.services.security.rate_limiter import MemoryRateLimiter

        limiter = MemoryRateLimiter()

        for _ in range(2):
            limiter.check("k1", limit=2, window_seconds=60)
        for _ in range(2):
            limiter.check("k2", limit=2, window_seconds=60)

        assert limiter.check("k1", limit=2, window_seconds=60) is False
        assert limiter.check("k2", limit=2, window_seconds=60) is False

        limiter.clear("k1")

        # k1 reset, k2 still blocked
        assert limiter.check("k1", limit=2, window_seconds=60) is True
        assert limiter.check("k2", limit=2, window_seconds=60) is False


# ============================================================================
# Test 2 — Rate limit key generation
# ============================================================================


class TestRateLimitKey:
    """Test key generation logic."""

    def test_login_key_uses_ip(self):
        """Login scope uses IP-based key (no user dimension)."""
        from app.core.rate_limit import _make_rate_limit_key

        mock_request = _MockRequest(
            headers={},
            client_host="192.168.1.100",
        )
        key = _make_rate_limit_key(mock_request, scope="login", use_user=False)
        assert "login" in key
        assert "192.168.1.100" in key

    def test_chat_key_uses_user_when_authenticated(self):
        """Chat scope should use user-based key when authenticated."""
        from app.core.rate_limit import _make_rate_limit_key

        mock_request = _MockRequest(
            headers={"Authorization": "Bearer fake-token-abc123"},
            client_host="10.0.0.1",
        )
        key = _make_rate_limit_key(mock_request, scope="chat", use_user=True)
        assert "chat" in key

    def test_upload_key_uses_user_when_authenticated(self):
        """Upload scope should use user-based key when authenticated."""
        from app.core.rate_limit import _make_rate_limit_key

        mock_request = _MockRequest(
            headers={"Authorization": "Bearer another-token-xyz"},
            client_host="10.0.0.2",
        )
        key = _make_rate_limit_key(mock_request, scope="upload", use_user=True)
        assert "upload" in key


# ============================================================================
# Test 3 — rate_limit dependency behavior
# ============================================================================


class TestRateLimitDependency:
    """Test the FastAPI rate_limit dependency."""

    def test_dependency_returns_callable(self):
        """rate_limit() factory should return a callable dependency."""
        from app.core.rate_limit import rate_limit

        dep = rate_limit(limit=5, window_seconds=60, scope="test")
        assert callable(dep)

    def test_rate_limit_blocked_raises_429(self):
        """When limit exceeded, dependency should raise 429."""
        from app.core.rate_limit import rate_limit, _limiter

        _limiter.clear()

        # Create dependency
        check_fn = rate_limit(limit=2, window_seconds=60, scope="test-429", use_user=False)

        mock_request = _MockRequest(headers={}, client_host="1.1.1.1")

        # First 2 requests pass
        import asyncio

        async def _send(n):
            for _ in range(n):
                await check_fn(mock_request)

        asyncio.run(_send(2))

        # 3rd should raise 429
        from fastapi import HTTPException

        async def _third():
            with pytest.raises(HTTPException) as exc_info:
                await check_fn(mock_request)
            return exc_info.value

        exc = asyncio.run(_third())
        assert exc.status_code == 429
        assert "Too many requests" in exc.detail

    def test_different_ips_isolated(self):
        """Different IPs should have independent rate limits."""
        from app.core.rate_limit import rate_limit, _limiter

        _limiter.clear()

        check_fn = rate_limit(limit=2, window_seconds=60, scope="test-ip2", use_user=False)

        mock_req_a = _MockRequest(headers={}, client_host="10.0.0.1")
        mock_req_b = _MockRequest(headers={}, client_host="10.0.0.2")

        import asyncio

        async def _run():
            # User A exhausts their limit
            await check_fn(mock_req_a)
            await check_fn(mock_req_a)
            # User A 3rd should fail
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                await check_fn(mock_req_a)
            assert exc.value.status_code == 429

            # User B 1st should still succeed
            await check_fn(mock_req_b)

        asyncio.run(_run())


# ============================================================================
# Helpers
# ============================================================================


class _MockRequest:
    """Lightweight mock for fastapi.Request."""

    def __init__(self, headers=None, client_host="127.0.0.1"):
        self.headers = headers or {}
        self.client = _MockClient(host=client_host)
        self._state = {}


class _MockClient:
    def __init__(self, host="127.0.0.1"):
        self.host = host
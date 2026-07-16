"""Tests for Sprint 28 Step 2: JWT Blacklist & Session Security.

Run: cd backend && ..\\.venv\\Scripts\\python.exe -m pytest tests/test_jwt_blacklist.py -v
"""

import asyncio
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, ".")

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================================
# Helpers
# ============================================================================

def _make_user(**overrides):
    from app.models.user import User
    user = MagicMock(spec=User)
    user.id = 1
    user.username = "testuser"
    user.email = "test@example.com"
    user.password_hash = "hashed"
    user.role = "user"
    user.is_active = True
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = None
    return user


# ============================================================================
# Test 1 — JWT 正常登录（jti 存在）
# ============================================================================

class TestJWTWithJti:
    """Verify JWT token creation includes jti claim."""

    def test_token_contains_jti(self):
        """Token payload should contain a jti UUID."""
        from app.auth.jwt import create_access_token, decode_access_token

        token = create_access_token(user_id=42, role="user")
        payload = decode_access_token(token)

        assert "jti" in payload
        assert payload["sub"] == "42"
        assert payload["role"] == "user"
        assert len(payload["jti"]) == 36  # UUID 格式


# ============================================================================
# Test 2-3 — Token 撤销后检测
# ============================================================================

class TestTokenRevoke:
    """Test revoke_token and is_token_revoked."""

    def test_revoke_token_extracts_jti_correctly(self):
        """revoke_token correctly extracts jti and user_id from valid token."""
        from app.auth.jwt import create_access_token, decode_access_token
        from app.services.auth.token_service import _extract_jti_and_user_id

        token = create_access_token(user_id=42)
        jti, user_id, expires_at = _extract_jti_and_user_id(token)

        payload = decode_access_token(token)
        assert jti == payload["jti"]
        assert user_id == 42
        assert expires_at is not None

    def test_is_token_revoked_detects_entry(self):
        """is_token_revoked should return True when jti exists in DB."""
        from app.services.auth.token_service import is_token_revoked

        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = 1  # exists
                mock_exec.return_value = mock_result
                return await is_token_revoked(mock_db, "test-jti-xxx")

        result = asyncio.run(_run())
        assert result is True

    def test_is_token_revoked_not_found(self):
        """is_token_revoked should return False when jti not in DB."""
        from app.services.auth.token_service import is_token_revoked

        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = None
                mock_exec.return_value = mock_result
                return await is_token_revoked(mock_db, "nonexistent-jti")

        result = asyncio.run(_run())
        assert result is False


# ============================================================================
# Test 4 — get_current_user with blacklist check
# ============================================================================

class TestGetCurrentUserBlacklistCheck:
    """Test that get_current_user rejects blacklisted tokens."""

    def test_blacklisted_jti_returns_401(self):
        """When jti is in blacklist, get_current_user should raise 401."""
        from app.auth.jwt import create_access_token, decode_access_token
        from fastapi import HTTPException

        token = create_access_token(user_id=1)
        payload = decode_access_token(token)

        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            import app.auth.deps as deps_module
            with patch.object(deps_module, "decode_access_token", return_value=payload):
                with patch.object(deps_module, "is_token_revoked", return_value=True):
                    with pytest.raises(HTTPException) as exc_info:
                        await deps_module.get_current_user(token=token, db=mock_db)
                    return exc_info.value

        exc = asyncio.run(_run())
        assert exc.status_code == 401
        assert "revoked" in exc.detail.lower()

    def test_valid_token_passes_blacklist_check(self):
        """When jti is NOT in blacklist, get_current_user passes and returns user."""
        from app.auth.jwt import create_access_token, decode_access_token

        token = create_access_token(user_id=1)
        payload = decode_access_token(token)

        mock_db = AsyncMock(spec=AsyncSession)
        user = _make_user()

        async def _run():
            import app.auth.deps as deps_module

            with patch.object(deps_module, "decode_access_token", return_value=payload):
                with patch.object(deps_module, "is_token_revoked", return_value=False):
                    # Patch UserSession check: get_session_by_token_hash returns None
                    with patch.object(
                        deps_module, "get_session_by_token_hash", new_callable=AsyncMock
                    ) as mock_get_session:
                        mock_get_session.return_value = None

                        with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
                            mock_result = MagicMock()
                            mock_result.scalar_one_or_none.return_value = user
                            mock_exec.return_value = mock_result
                            return await deps_module.get_current_user(token=token, db=mock_db)

        result = asyncio.run(_run())
        assert result is user


# ============================================================================
# Test 5 — revoke_user_tokens batch revocation
# ============================================================================

class TestRevokeUserTokens:
    """Test batch token revocation when disabling a user."""

    def test_revoke_user_tokens_calls_revoke_session(self):
        """revoke_user_tokens should call revoke_session for each active session."""
        from app.services.auth.token_service import revoke_user_tokens
        from app.models.user_session import UserSession

        mock_db = AsyncMock(spec=AsyncSession)

        session1 = MagicMock(spec=UserSession)
        session1.id = 1
        session1.revoked_at = None
        session2 = MagicMock(spec=UserSession)
        session2.id = 2
        session2.revoked_at = None

        async def _run():
            with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
                mock_result = MagicMock()
                mock_result.scalars.return_value.all.return_value = [session1, session2]
                mock_exec.return_value = mock_result

                # Patch revoke_session (imported from ..session_service) to avoid inner DB calls
                with patch(
                    "app.services.session_service.revoke_session", new_callable=AsyncMock
                ) as mock_revoke:
                    return await revoke_user_tokens(mock_db, user_id=42, reason="admin_disable")

        count = asyncio.run(_run())
        assert count == 2

    def test_revoke_user_tokens_empty(self):
        """revoke_user_tokens returns 0 when user has no active sessions."""
        from app.services.auth.token_service import revoke_user_tokens

        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
                mock_result = MagicMock()
                mock_result.scalars.return_value.all.return_value = []
                mock_exec.return_value = mock_result
                return await revoke_user_tokens(mock_db, user_id=99, reason="admin_disable")

        count = asyncio.run(_run())
        assert count == 0


# ============================================================================
# Test 6 — Logout API endpoint
# ============================================================================

class TestLogoutEndpoint:
    """Test the /api/auth/logout endpoint."""

    def test_logout_revokes_token_and_returns_success(self):
        """Logout should call revoke_token and return success message."""
        import app.api.auth as auth_module

        token = "fake-jwt-token-string"
        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            with patch.object(auth_module, "revoke_token", new_callable=AsyncMock) as mock_revoke:
                result = await auth_module.logout(token=token, db=mock_db)
                mock_revoke.assert_called_once_with(mock_db, token, reason="logout")
                return result

        result = asyncio.run(_run())
        assert result.message == "已成功退出登录"

    def test_logout_handles_invalid_token_gracefully(self):
        """Logout should not raise even if token is invalid/expired."""
        import app.api.auth as auth_module

        token = "expired-or-invalid-token"
        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            with patch.object(auth_module, "revoke_token", side_effect=Exception("invalid")):
                result = await auth_module.logout(token=token, db=mock_db)
                return result

        result = asyncio.run(_run())
        assert result.message == "已成功退出登录"


# ============================================================================
# Test 7 — Backward compatibility: tokens without jti still work
# ============================================================================

class TestBackwardCompatibility:
    """Test that tokens without jti still work (backward compatibility)."""

    def test_token_without_jti_passes_blacklist_check(self):
        """Token without jti claim should skip blacklist check and proceed."""
        payload_without_jti = {
            "sub": "1",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc).timestamp() + 3600,
        }

        mock_db = AsyncMock(spec=AsyncSession)
        user = _make_user()

        async def _run():
            import app.auth.deps as deps_module

            with patch.object(deps_module, "decode_access_token", return_value=payload_without_jti):
                # jti is None, so is_token_revoked should NOT be called
                with patch.object(deps_module, "get_session_by_token_hash", new_callable=AsyncMock) as mock_gs:
                    mock_gs.return_value = None

                    with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
                        mock_result = MagicMock()
                        mock_result.scalar_one_or_none.return_value = user
                        mock_exec.return_value = mock_result
                        return await deps_module.get_current_user(token="legacy-token", db=mock_db)

        result = asyncio.run(_run())
        assert result is user
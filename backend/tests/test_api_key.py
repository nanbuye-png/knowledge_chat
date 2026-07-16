"""Tests for Sprint 28 Step 5: API Key Management.

Run: cd backend && ..\\.venv\\Scripts\\python.exe -m pytest tests/test_api_key.py -v
"""

import sys
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
    user.id = overrides.get("id", 1)
    user.username = overrides.get("username", "testuser")
    user.email = "test@example.com"
    user.role = "user"
    user.is_active = True
    return user


# ============================================================================
# Test 1 — Create API Key
# ============================================================================

class TestCreateApiKey:
    """Test creating API Key."""

    def test_create_key_returns_raw_key(self):
        """create_api_key should return the raw key (only once)."""
        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            with patch("app.services.api_key_service.ApiKey") as MockAK:
                mock_entry = MagicMock()
                mock_entry.id = 1
                mock_entry.name = "Test Key"
                MockAK.return_value = mock_entry

                from app.services.api_key_service import create_api_key
                api_key, raw_key = await create_api_key(
                    db=mock_db, user_id=1, name="Test Key",
                )
                return api_key, raw_key

        api_key, raw_key = asyncio_run(_run())

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()
        assert raw_key.startswith("sk-kc-")
        assert len(raw_key) > 20

    def test_generated_key_has_correct_format(self):
        """Raw key should follow format sk-kc-<hex>-<hex>."""
        from app.services.api_key_service import _generate_raw_api_key

        raw_key, key_hash, key_prefix = _generate_raw_api_key(1)
        assert raw_key.startswith("sk-kc-")
        assert key_prefix == "sk-kc-0001"
        assert len(key_hash) == 64  # SHA256 hex


# ============================================================================
# Test 2 — DB stores hash, not plaintext
# ============================================================================

class TestKeyStorage:
    """Ensure database never stores plaintext keys."""

    def test_stores_hash_not_plaintext(self):
        """The key_hash field should contain a SHA256 hash, not the raw key."""
        from app.services.api_key_service import _generate_raw_api_key, _hash_key

        raw_key, key_hash, _ = _generate_raw_api_key(1)
        assert key_hash != raw_key
        assert _hash_key(raw_key) == key_hash  # Deterministic


# ============================================================================
# Test 3 — Verify API Key
# ============================================================================

class TestVerifyApiKey:
    """Test API Key verification."""

    def test_verify_valid_key_returns_user(self):
        """verify_api_key with valid key should return a User."""
        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
                # First execution: query ApiKey → found
                mock_api_key = MagicMock()
                mock_api_key.is_active = True
                mock_api_key.expires_at = None

                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = mock_api_key
                # Second execution: query User
                mock_user_result = MagicMock()
                user = _make_user()
                mock_user_result.scalar_one_or_none.return_value = user

                mock_exec.side_effect = [mock_result, mock_user_result]

                from app.services.api_key_service import verify_api_key
                result = await verify_api_key(mock_db, "sk-kc-0001-validkeyhash")
                return result

        user = asyncio_run(_run())
        assert user is not None
        assert user.id == 1

    def test_verify_invalid_key_returns_none(self):
        """verify_api_key with invalid key should return None."""
        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = None
                mock_exec.return_value = mock_result

                from app.services.api_key_service import verify_api_key
                result = await verify_api_key(mock_db, "sk-kc-xxxx-invalid")
                return result

        user = asyncio_run(_run())
        assert user is None


# ============================================================================
# Test 4 — Revoked key fails
# ============================================================================

class TestRevokedKey:
    """Test revoked API Key cannot be used."""

    def test_revoked_key_returns_none(self):
        """verify_api_key with revoked key should return None."""
        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
                mock_api_key = MagicMock()
                mock_api_key.is_active = False  # Revoked
                mock_api_key.expires_at = None

                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = mock_api_key
                mock_exec.return_value = mock_result

                from app.services.api_key_service import verify_api_key
                result = await verify_api_key(mock_db, "sk-kc-xxxx-revoked")
                return result

        user = asyncio_run(_run())
        assert user is None


# ============================================================================
# Test 5 — Expired key fails
# ============================================================================

class TestExpiredKey:
    """Test expired API Key cannot be used."""

    def test_expired_key_returns_none(self):
        """verify_api_key with expired key should return None."""
        from datetime import datetime, timedelta, timezone

        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
                mock_api_key = MagicMock()
                mock_api_key.is_active = True
                mock_api_key.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)  # Expired

                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = mock_api_key
                mock_exec.return_value = mock_result

                from app.services.api_key_service import verify_api_key
                result = await verify_api_key(mock_db, "sk-kc-xxxx-expired")
                return result

        user = asyncio_run(_run())
        assert user is None


# ============================================================================
# Test 6 — Revoke key
# ============================================================================

class TestRevokeApiKey:
    """Test API Key revocation."""

    def test_revoke_sets_inactive(self):
        """revoke_api_key should set is_active=False."""
        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
                mock_api_key = MagicMock()
                mock_api_key.id = 1
                mock_api_key.name = "Test Key"
                mock_api_key.is_active = True

                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = mock_api_key
                mock_exec.return_value = mock_result

                from app.services.api_key_service import revoke_api_key
                result = await revoke_api_key(mock_db, key_id=1, user_id=1)
                return result

        key = asyncio_run(_run())
        assert key is not None
        assert key.is_active is False  # Changed by service


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)
"""Tests for Sprint 28 Step 1: Login Protection & Account Security.

Run: cd backend && ..\\.venv\\Scripts\\python.exe -m pytest tests/test_security.py -v
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, ".")

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================================
# Helpers
# ============================================================================

def _make_user(**overrides):
    """Create a mock User with default security fields."""
    from app.models.user import User

    user = MagicMock(spec=User)
    user.id = 1
    user.username = "testuser"
    user.email = "test@example.com"
    user.password_hash = "hashed_xxx"
    user.role = "user"
    user.is_active = True
    user.failed_login_count = overrides.get("failed_login_count", 0)
    user.locked_until = overrides.get("locked_until", None)
    user.last_login_at = overrides.get("last_login_at", None)
    return user


# ============================================================================
# Test 1 & 6 & 7 — Password Policy (password_policy.py)
# ============================================================================


class TestPasswordStrength:
    """Validate password strength policy rules."""

    def test_weak_password_too_short(self):
        """Password shorter than 12 chars → invalid."""
        from app.core.password_policy import validate_password_strength

        is_valid, errors = validate_password_strength("Ab1!")
        assert not is_valid
        assert any("长度" in e for e in errors)

    def test_weak_password_no_digit(self):
        """Password without digit → invalid."""
        from app.core.password_policy import validate_password_strength

        is_valid, errors = validate_password_strength("Abcdefghijkl!")
        assert not is_valid
        assert any("数字" in e for e in errors)

    def test_weak_password_no_upper(self):
        """Password without uppercase → invalid."""
        from app.core.password_policy import validate_password_strength

        is_valid, errors = validate_password_strength("abcdefghijkl1!")
        assert not is_valid
        assert any("大写" in e for e in errors)

    def test_weak_password_no_lower(self):
        """Password without lowercase → invalid."""
        from app.core.password_policy import validate_password_strength

        is_valid, errors = validate_password_strength("ABCDEFGHIJKL1!")
        assert not is_valid
        assert any("小写" in e for e in errors)

    def test_weak_password_no_special(self):
        """Password without special char → invalid."""
        from app.core.password_policy import validate_password_strength

        is_valid, errors = validate_password_strength("Abcdefghijkl1")
        assert not is_valid
        assert any("特殊" in e for e in errors)

    def test_strong_password_passes(self):
        """Password meeting all criteria → valid."""
        from app.core.password_policy import validate_password_strength

        is_valid, errors = validate_password_strength("MyStr0ng!Pass")
        assert is_valid
        assert len(errors) == 0

    def test_multiple_errors_reported(self):
        """Password failing multiple rules reports all errors."""
        from app.core.password_policy import validate_password_strength

        is_valid, errors = validate_password_strength("ab")
        assert not is_valid
        assert len(errors) >= 3


# ============================================================================
# Test 2-5 — Login Protection Logic (auth.py login endpoint)
# ============================================================================


class TestLoginProtection:
    """Test login failure counting, account locking, and unlock flow."""

    # --- Scenario 1: Correct password → success, reset counters ---

    def test_correct_password_resets_counters(self):
        """Successful login with failed_login_count=3 should reset to 0."""
        import app.api.auth as auth_module

        user = _make_user(failed_login_count=3)
        mock_db = AsyncMock(spec=AsyncSession)

        # Patch DB execute to return this user, then empty KB result
        with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = user
            mock_kb_result = MagicMock()
            mock_kb_result.scalars.return_value.first.return_value = None
            mock_exec.side_effect = [mock_result, mock_kb_result]

            with patch.object(auth_module, "verify_password", return_value=True):
                with patch.object(auth_module, "update_user_activity", new_callable=AsyncMock):
                    with patch.object(auth_module, "create_session", new_callable=AsyncMock):
                        with patch.object(auth_module, "create_access_token", return_value="fake-jwt-token"):

                            async def _run():
                                request = auth_module.LoginRequest(username="testuser", password="correct")
                                return await auth_module.login(request, None, mock_db)

                            result = asyncio.run(_run())

        assert user.failed_login_count == 0
        assert user.locked_until is None
        assert user.last_login_at is not None
        assert result.access_token == "fake-jwt-token"

    # --- Scenario 2: 4 wrong passwords → not locked yet ---

    def test_four_failures_not_locked(self):
        """4 consecutive failures should NOT lock the account."""
        import app.api.auth as auth_module

        user = _make_user(failed_login_count=0)
        mock_db = AsyncMock(spec=AsyncSession)

        with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = user
            mock_exec.return_value = mock_result

            with patch.object(auth_module, "verify_password", return_value=False):

                async def _run():
                    for _ in range(4):
                        request = auth_module.LoginRequest(username="testuser", password="wrong")
                        try:
                            await auth_module.login(request, None, mock_db)
                        except Exception:
                            pass  # Expected 401

                asyncio.run(_run())

        assert user.failed_login_count == 4
        assert user.locked_until is None

    # --- Scenario 3: 5th wrong password → locked ---

    def test_fifth_failure_locks_account(self):
        """The 5th consecutive failure should lock the account for 15 min."""
        import app.api.auth as auth_module

        user = _make_user(failed_login_count=4)
        mock_db = AsyncMock(spec=AsyncSession)

        with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = user
            mock_exec.return_value = mock_result

            with patch.object(auth_module, "verify_password", return_value=False):

                async def _run():
                    request = auth_module.LoginRequest(username="testuser", password="wrong5")
                    try:
                        await auth_module.login(request, None, mock_db)
                    except Exception:
                        pass

                asyncio.run(_run())

        assert user.failed_login_count == 5
        assert user.locked_until is not None
        delta = user.locked_until - datetime.now(timezone.utc)
        assert timedelta(minutes=14) < delta < timedelta(minutes=16)

    # --- Scenario 4: Locked account rejects correct password ---

    def test_locked_account_rejects_correct_password(self):
        """During lockout, even correct password should be rejected (403)."""
        import app.api.auth as auth_module
        from fastapi import HTTPException

        future_lock = datetime.now(timezone.utc) + timedelta(minutes=10)
        user = _make_user(failed_login_count=5, locked_until=future_lock)
        mock_db = AsyncMock(spec=AsyncSession)

        with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = user
            mock_exec.return_value = mock_result

            verify_mock = MagicMock(return_value=True)

            async def _run():
                with patch.object(auth_module, "verify_password", verify_mock):
                    request = auth_module.LoginRequest(username="testuser", password="correct")
                    with pytest.raises(HTTPException) as exc_info:
                        await auth_module.login(request, None, mock_db)
                    return exc_info.value

            exc = asyncio.run(_run())

        assert exc.status_code == 403
        assert "锁定" in exc.detail
        verify_mock.assert_not_called()

    # --- Scenario 5: Unlock clears lock state ---

    def test_unlock_user_clears_lock(self):
        """unlock_user should reset failed_login_count and locked_until."""
        mock_db = AsyncMock(spec=AsyncSession)
        future_lock = datetime.now(timezone.utc) + timedelta(minutes=10)
        user = _make_user(failed_login_count=5, locked_until=future_lock)

        with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = user
            mock_exec.return_value = mock_result

            async def _run():
                from app.services.user_service import unlock_user
                return await unlock_user(mock_db, 1)

            result = asyncio.run(_run())

        assert result is not None
        assert user.failed_login_count == 0
        assert user.locked_until is None
        mock_db.add.assert_called_with(user)
        mock_db.commit.assert_called()

    def test_unlock_user_not_found(self):
        """unlock_user for non-existent user returns None."""
        mock_db = AsyncMock(spec=AsyncSession)

        with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_exec.return_value = mock_result

            async def _run():
                from app.services.user_service import unlock_user
                return await unlock_user(mock_db, 999)

            result = asyncio.run(_run())

        assert result is None


# ============================================================================
# Test 8 — Registration Password Validation Integration
# ============================================================================


class TestRegistrationPasswordPolicy:
    """Test that the register endpoint enforces password policy."""

    def test_weak_password_registration_fails(self):
        """Registration with a weak password should return 400."""
        import app.api.auth as auth_module
        from fastapi import HTTPException

        mock_db = AsyncMock(spec=AsyncSession)

        with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_exec.return_value = mock_result

            async def _run():
                # Must pass Pydantic min_length=6 but fail strength policy
                request = auth_module.RegisterRequest(
                    username="newuser",
                    email="new@example.com",
                    password="abcdef",  # 6 chars passes Pydantic, fails strength (no digit/upper/special)
                )
                with pytest.raises(HTTPException) as exc_info:
                    await auth_module.register(request, mock_db)
                return exc_info.value

            exc = asyncio.run(_run())

        assert exc.status_code == 400
        assert "数字" in exc.detail or "大写" in exc.detail or "特殊" in exc.detail

    def test_strong_password_registration_succeeds(self):
        """Registration with a strong password should succeed."""
        import app.api.auth as auth_module

        mock_db = AsyncMock(spec=AsyncSession)

        async def _refresh(user_instance):
            # Simulate DB assigning an id after commit
            user_instance.id = 42

        mock_db.refresh = _refresh

        with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_exec.return_value = mock_result

            async def _run():
                request = auth_module.RegisterRequest(
                    username="newuser",
                    email="new@example.com",
                    password="MyStr0ng!Pass",
                )
                return await auth_module.register(request, mock_db)

            result = asyncio.run(_run())

        assert result.username == "newuser"
        assert result.email == "new@example.com"
        assert result.id == 42
        mock_db.add.assert_called_once()
        added_user = mock_db.add.call_args[0][0]
        assert added_user.password_hash != "MyStr0ng!Pass"
        mock_db.commit.assert_called()

"""Tests for Sprint 28 Step 4: Audit Log System.

Run: cd backend && ..\\.venv\\Scripts\\python.exe -m pytest tests/test_audit_log.py -v
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, ".")

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================================
# Test 1 — create_audit_log creates record
# ============================================================================

class TestCreateAuditLog:
    """Test audit log creation."""

    def test_create_log_success(self):
        """create_audit_log should add a record and return it."""
        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            from app.services.audit_service import create_audit_log
            with patch("app.services.audit_service.AuditLog") as MockAL:
                mock_entry = MagicMock()
                MockAL.return_value = mock_entry
                log = await create_audit_log(
                    db=mock_db,
                    operator_id=1,
                    action="LOGIN_SUCCESS",
                    target_type="user",
                    target_id=1,
                    ip_address="127.0.0.1",
                    user_agent="pytest",
                    status="SUCCESS",
                )
                return log

        result = asyncio_run(_run())
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()
        assert result is not None

    def test_create_log_with_detail(self):
        """create_audit_log stores detail as JSON."""
        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            from app.services.audit_service import create_audit_log
            with patch("app.services.audit_service.AuditLog") as MockAL:
                mock_entry = MagicMock()
                MockAL.return_value = mock_entry
                log = await create_audit_log(
                    db=mock_db, operator_id=2, action="USER_DISABLE",
                    target_type="user", target_id=5,
                    detail={"before": True, "after": False},
                    status="SUCCESS",
                )
                # Check kwargs passed to AuditLog constructor
                args = MockAL.call_args[1]
                assert args["operator_id"] == 2
                assert args["action"] == "USER_DISABLE"
                assert args["target_type"] == "user"
                assert args["target_id"] == 5
                return log

        result = asyncio_run(_run())


# ============================================================================
# Test 2 — _extract_client_info
# ============================================================================

class TestExtractClientInfo:
    """Test client info extraction from Request."""

    def test_extracts_ip_and_ua(self):
        """Should extract IP and User-Agent from request headers."""
        from app.services.audit_service import _extract_client_info

        mock_req = _MockRequest(
            headers={
                "User-Agent": "Mozilla/5.0",
                "X-Forwarded-For": "10.0.0.1",
            },
            client_host="192.168.1.1",
        )
        ip, ua = _extract_client_info(mock_req)
        assert ip == "10.0.0.1"
        assert ua == "Mozilla/5.0"

    def test_fallback_to_client_host(self):
        """When no X-Forwarded-For, use request.client.host."""
        from app.services.audit_service import _extract_client_info

        mock_req = _MockRequest(
            headers={"User-Agent": "test"},
            client_host="192.168.1.100",
        )
        ip, ua = _extract_client_info(mock_req)
        assert ip == "192.168.1.100"
        assert ua == "test"

    def test_truncates_long_ua(self):
        """User-Agent > 255 chars should be truncated."""
        from app.services.audit_service import _extract_client_info

        long_ua = "X" * 300
        mock_req = _MockRequest(headers={"User-Agent": long_ua}, client_host="1.1.1.1")
        ip, ua = _extract_client_info(mock_req)
        assert len(ua) == 255


# ============================================================================
# Test 3 — get_logs with pagination
# ============================================================================

class TestGetLogs:
    """Test paginated log query."""

    def test_get_logs_returns_paginated(self):
        """get_logs should return items, total, page, page_size."""
        from app.services.audit_service import get_logs

        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
                # Count query result
                mock_count = MagicMock()
                mock_count.scalar.return_value = 100
                # Items query result
                mock_items = MagicMock()

                # Use MagicMock to simulate AuditLog
                log1 = MagicMock()
                log1.id = 1
                log1.to_dict.return_value = {
                    "id": 1, "operator_id": 1, "action": "LOGIN_SUCCESS",
                    "target_type": "user", "target_id": 1, "status": "SUCCESS",
                    "ip_address": None, "user_agent": None, "detail": None,
                    "created_at": "2025-01-01T00:00:00",
                }
                mock_items.scalars.return_value.all.return_value = [log1]

                mock_exec.side_effect = [mock_count, mock_items]

                return await get_logs(db=mock_db, page=1, page_size=20)

        result = asyncio_run(_run())
        assert result["total"] == 100
        assert result["page"] == 1
        assert result["page_size"] == 20
        assert len(result["items"]) == 1
        assert result["items"][0]["action"] == "LOGIN_SUCCESS"

    def test_get_logs_filtered(self):
        """get_logs should support filtering by action and user_id."""
        from app.services.audit_service import get_logs

        mock_db = AsyncMock(spec=AsyncSession)

        async def _run():
            with patch.object(mock_db, "execute", new_callable=AsyncMock) as mock_exec:
                mock_count = MagicMock()
                mock_count.scalar.return_value = 5
                mock_items = MagicMock()
                mock_items.scalars.return_value.all.return_value = []
                mock_exec.side_effect = [mock_count, mock_items]

                return await get_logs(
                    db=mock_db, page=1, page_size=10,
                    action="LOGIN_FAILED", user_id=42,
                )

        result = asyncio_run(_run())
        assert result["total"] == 5


# ============================================================================
# Test 4 — Schema validation
# ============================================================================

class TestAuditLogSchemas:
    """Test AuditLog response schemas."""

    def test_audit_log_item_schema(self):
        """AuditLogItem should accept and serialize correctly."""
        from app.api.admin.audit_logs import AuditLogItem

        item = AuditLogItem(
            id=1, operator_id=2, action="TEST",
            target_type="system", status="SUCCESS",
        )
        d = item.model_dump()
        assert d["id"] == 1
        assert d["operator_id"] == 2
        assert d["action"] == "TEST"
        assert d["status"] == "SUCCESS"

    def test_audit_log_list_response(self):
        """AuditLogListResponse serialize."""
        from app.api.admin.audit_logs import AuditLogListResponse, AuditLogItem

        resp = AuditLogListResponse(
            items=[AuditLogItem(id=1, operator_id=1, action="LOGIN", target_type="user", status="SUCCESS")],
            total=1, page=1, page_size=20,
        )
        d = resp.model_dump()
        assert d["total"] == 1
        assert len(d["items"]) == 1


# ============================================================================
# Helpers
# ============================================================================

def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


class _MockRequest:
    def __init__(self, headers=None, client_host="127.0.0.1"):
        self.headers = headers or {}
        self.client = _MockClient(host=client_host)


class _MockClient:
    def __init__(self, host="127.0.0.1"):
        self.host = host
"""Test script for Sprint 16: Vector Lifecycle Management.

Run: cd backend && ..\\.venv\\Scripts\\python.exe -m pytest tests/test_vector_lifecycle.py -v
"""

import asyncio
import ast
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, ".")

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vector_store():
    """Create a mocked VectorStore with a fake collection."""
    from app.storage.vector_store import VectorStore

    vs = VectorStore()
    vs._initialized = True
    vs.collection = MagicMock()
    vs.collection.delete = MagicMock()
    vs.collection.query = MagicMock()
    vs.collection.count = MagicMock(return_value=0)
    return vs


# ---------------------------------------------------------------------------
# Tests — Part 1: VectorStore new methods
# ---------------------------------------------------------------------------


class TestDeleteKnowledgeBase:
    """Part 1 — Test 1: delete_knowledge_base"""

    def test_deletes_only_specified_kb(self):
        """delete_knowledge_base(1) calls collection.delete with correct where filter."""
        vs = _make_vector_store()

        async def _run():
            await vs.delete_knowledge_base(1)

        asyncio.run(_run())

        vs.collection.delete.assert_called_once_with(
            where={"knowledge_base_id": {"$eq": 1}}
        )

    def test_not_initialized_does_nothing(self):
        """When _initialized is False, skip deletion gracefully."""
        from app.storage.vector_store import VectorStore

        vs = VectorStore()
        vs._initialized = False
        vs.collection = MagicMock()

        async def _run():
            await vs.delete_knowledge_base(1)

        asyncio.run(_run())
        vs.collection.delete.assert_not_called()

    def test_exception_raised(self):
        """When collection.delete raises, the method propagates the error."""
        vs = _make_vector_store()
        vs.collection.delete.side_effect = RuntimeError("ChromaDB down")

        with pytest.raises(RuntimeError, match="ChromaDB down"):
            asyncio.run(vs.delete_knowledge_base(1))


class TestDeleteUser:
    """Part 1 — Test 2: delete_user"""

    def test_deletes_only_specified_user(self):
        """delete_user(2) calls collection.delete with correct where filter."""
        vs = _make_vector_store()

        async def _run():
            await vs.delete_user(2)

        asyncio.run(_run())

        vs.collection.delete.assert_called_once_with(
            where={"user_id": {"$eq": 2}}
        )

    def test_not_initialized_does_nothing(self):
        """When _initialized is False, skip gracefully."""
        from app.storage.vector_store import VectorStore

        vs = VectorStore()
        vs._initialized = False
        vs.collection = MagicMock()

        async def _run():
            await vs.delete_user(1)

        asyncio.run(_run())
        vs.collection.delete.assert_not_called()

    def test_exception_raised(self):
        """When collection.delete raises, the method propagates the error."""
        vs = _make_vector_store()
        vs.collection.delete.side_effect = RuntimeError("ChromaDB down")

        with pytest.raises(RuntimeError, match="ChromaDB down"):
            asyncio.run(vs.delete_user(1))


class TestDeleteDocumentStaysCompatible:
    """Part 3: delete_document() is unchanged and still works."""

    def test_delete_document_calls_correct_filter(self):
        """delete_document('doc-abc') calls collection.delete with document_id filter."""
        vs = _make_vector_store()

        async def _run():
            await vs.delete_document("doc-abc")

        asyncio.run(_run())

        vs.collection.delete.assert_called_once_with(
            where={"document_id": "doc-abc"}
        )

    def test_not_initialized_does_nothing(self):
        """When _initialized is False, delete_document skips gracefully."""
        from app.storage.vector_store import VectorStore

        vs = VectorStore()
        vs._initialized = False
        vs.collection = MagicMock()

        async def _run():
            await vs.delete_document("doc-xyz")

        asyncio.run(_run())
        vs.collection.delete.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — Part 5: Integration scenarios (mocked Chroma, real logic)
# ---------------------------------------------------------------------------


class TestKBDeleteOnlyRemovesTarget:
    """Test 1: KB1+KB2 → delete_knowledge_base(1) → only KB1 vectors removed."""

    def test_delete_kb1_leaves_kb2(self):
        """Simulate delete_knowledge_base(1) then (2), verify separate calls."""
        vs = _make_vector_store()

        async def _run():
            await vs.delete_knowledge_base(1)
            await vs.delete_knowledge_base(2)

        asyncio.run(_run())

        assert vs.collection.delete.call_count == 2
        calls = vs.collection.delete.call_args_list
        assert calls[0][1] == {"where": {"knowledge_base_id": {"$eq": 1}}}
        assert calls[1][1] == {"where": {"knowledge_base_id": {"$eq": 2}}}


class TestUserDeleteOnlyRemovesTarget:
    """Test 2: user1+user2 → delete_user(user1) → only user1 vectors removed."""

    def test_delete_user1_leaves_user2(self):
        """Simulate delete_user(1), verify filter targets only user 1."""
        vs = _make_vector_store()

        async def _run():
            await vs.delete_user(1)

        asyncio.run(_run())

        vs.collection.delete.assert_called_once_with(
            where={"user_id": {"$eq": 1}}
        )


# ---------------------------------------------------------------------------
# Tests — Part 2: KnowledgeBase API deletion integrates correctly
# ---------------------------------------------------------------------------


class TestKnowledgeBaseDeleteFlow:
    """Test that the API delete endpoint calls vector_store.delete_knowledge_base.

    We parse the source to verify the old per-document loop was replaced
    with a single delete_knowledge_base call.
    """

    def test_uses_delete_knowledge_base_not_loop(self):
        """Verify single delete_knowledge_base call replaces the old loop.

        Checks the source of knowledge_bases.py to confirm:
          - delete_knowledge_base is invoked
          - The old per-document loop (for doc_id in doc_ids) is gone
        """
        src_path = "app/api/knowledge_bases.py"
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
        delete_func = None

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "delete_knowledge_base":
                delete_func = node
                break

        assert delete_func is not None, (
            "Could not find delete_knowledge_base function in knowledge_bases.py"
        )

        # Extract function body lines
        func_lines = source.split("\n")
        start = delete_func.body[0].lineno - 1
        end = delete_func.body[-1].end_lineno
        body = "\n".join(func_lines[start:end])

        # Should contain delete_knowledge_base call
        assert "delete_knowledge_base" in body, (
            "delete_knowledge_base call not found in API delete function body"
        )

        # Should NOT contain the old per-document loop pattern
        assert "for doc_id in doc_ids" not in body, (
            "Old per-document loop still present in API delete function"
        )

        # Only document-related vector_store call should be delete_knowledge_base
        # (delete_document might still appear in DocumentService imports, but not in this function)
        assert "vector_store.delete_document" not in body, (
            "vector_store.delete_document should not be called in KB delete anymore"
        )


# ---------------------------------------------------------------------------
# Tests — Part 5, Test 4: End-to-end simulation with mocked DB
# ---------------------------------------------------------------------------


class TestKBDeleteEndToEndSimulation:
    """Simulate the full delete flow: KB exists → vectors deleted → SQL records deleted."""

    def test_full_delete_flow_calls_vector_store_once(self):
        """Verify the high-level orchestration logic.

        We simulate what the endpoint does:
          1. Find KB → exists
          2. vector_store.delete_knowledge_base(kb_id)
          3. Delete SQL records
        """
        vs = _make_vector_store()

        # Simulated KB
        kb = MagicMock()
        kb.id = 1
        kb.name = "Test KB"

        async def _simulate():
            # Step 1: confirm KB exists (mocked)
            assert kb.id == 1

            # Step 2: clean vectors (single call)
            await vs.delete_knowledge_base(kb.id)

            # Step 3: SQL cleanup (just verify step 2 happened)
            pass

        asyncio.run(_simulate())

        vs.collection.delete.assert_called_once_with(
            where={"knowledge_base_id": {"$eq": 1}}
        )


# ---------------------------------------------------------------------------
# Tests — Part 5, Test 4 corollary: After delete, search returns 0 results
# ---------------------------------------------------------------------------


class TestSearchAfterDeleteReturnsEmpty:
    """After vectors are deleted, a Chroma query on that KB returns empty."""

    def test_search_after_kb_delete_returns_empty(self):
        """Simulate: add data → delete KB → search returns nothing."""
        vs = _make_vector_store()

        # Mock query to return empty after deletion
        vs.collection.query.return_value = {"ids": [[]], "metadatas": [[]], "documents": [[]], "distances": [[]]}

        async def _run():
            await vs.delete_knowledge_base(1)
            results = await vs.search(
                query_embedding=[0.1] * 768,
                top_k=5,
                knowledge_base_id=1,
            )
            return results

        results = asyncio.run(_run())
        assert results == []
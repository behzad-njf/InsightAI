"""Unit tests for in-memory chat session store."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from insightai.domain.exceptions import ChatSessionNotFoundError
from insightai.domain.models.chat_session import ChatMessage, ChatMessageRole
from insightai.infrastructure.chat.memory_session_store import MemoryChatSessionStore


@pytest.fixture
def store() -> MemoryChatSessionStore:
    return MemoryChatSessionStore(ttl_seconds=3600, max_messages_per_session=10)


@pytest.mark.asyncio
async def test_create_and_list_messages(store: MemoryChatSessionStore) -> None:
    session = await store.create_session(title="Test")
    assert session.title == "Test"
    assert session.message_count == 0

    msg = ChatMessage(
        id="m1",
        session_id=session.id,
        role=ChatMessageRole.USER,
        content="Hello",
        created_at=datetime.now(UTC),
    )
    await store.append_message(msg)
    messages = await store.list_messages(session.id)
    assert len(messages) == 1
    assert messages[0].content == "Hello"

    updated = await store.get_session(session.id)
    assert updated is not None
    assert updated.message_count == 1


@pytest.mark.asyncio
async def test_append_unknown_session_raises(store: MemoryChatSessionStore) -> None:
    msg = ChatMessage(
        id="m1",
        session_id="00000000-0000-0000-0000-000000000000",
        role=ChatMessageRole.USER,
        content="Hi",
        created_at=datetime.now(UTC),
    )
    with pytest.raises(ChatSessionNotFoundError):
        await store.append_message(msg)


@pytest.mark.asyncio
async def test_delete_session(store: MemoryChatSessionStore) -> None:
    session = await store.create_session()
    assert await store.delete_session(session.id) is True
    assert await store.get_session(session.id) is None
    assert await store.delete_session(session.id) is False

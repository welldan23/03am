"""State antarmuka chat yang harus selamat dari restart: update yang sudah diproses dan
konteks percakapan per chat."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from studio.infra.db import Database
from studio.shared.clock import Clock, from_iso, to_iso

IDLE = "idle"


class UpdateLog:
    """Deduplikasi update dari kanal chat (Telegram bisa mengirim ulang update yang sama)."""

    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    def register(self, channel: str, update_id: int) -> bool:
        """True kalau update baru; False kalau sudah pernah diproses."""
        with self._db.transaction():
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO ui_processed_updates (channel, update_id, received_at)"
                " VALUES (?, ?, ?)",
                (channel, update_id, to_iso(self._clock.now())),
            )
        return cursor.rowcount == 1

    def prune(self, *, older_than: timedelta) -> int:
        cutoff = to_iso(self._clock.now() - older_than)
        with self._db.transaction():
            cursor = self._db.execute(
                "DELETE FROM ui_processed_updates WHERE received_at <= ?", (cutoff,)
            )
        return cursor.rowcount


@dataclass(frozen=True)
class Conversation:
    channel: str
    chat_id: str
    actor: str
    state: str = IDLE
    data: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None

    @property
    def current_episode_id(self) -> str | None:
        value = self.data.get("episode_id")
        return str(value) if value else None


class ConversationStore:
    """Satu baris per chat. State sementara (misal menunggu catatan revisi) kedaluwarsa
    sendiri; episode yang sedang dibahas tetap diingat."""

    def __init__(self, db: Database, clock: Clock, *, step_ttl: timedelta) -> None:
        self._db = db
        self._clock = clock
        self._step_ttl = step_ttl

    def get(self, channel: str, chat_id: str, actor: str) -> Conversation:
        row = self._db.query_one(
            "SELECT * FROM ui_conversations WHERE channel = ? AND chat_id = ?", (channel, chat_id)
        )
        if row is None or row["actor"] != actor:
            return Conversation(channel, chat_id, actor)
        data = json.loads(row["data"])
        updated = from_iso(row["updated_at"])
        state = row["state"]
        if state != IDLE and self._clock.now() - updated > self._step_ttl:
            state = IDLE
            data = {k: v for k, v in data.items() if k == "episode_id"}
        return Conversation(channel, chat_id, actor, state, data, updated)

    def save(self, conversation: Conversation) -> Conversation:
        now = self._clock.now()
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO ui_conversations (channel, chat_id, actor, state, data, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (channel, chat_id) DO UPDATE SET"
                " actor = excluded.actor, state = excluded.state, data = excluded.data,"
                " updated_at = excluded.updated_at",
                (
                    conversation.channel,
                    conversation.chat_id,
                    conversation.actor,
                    conversation.state,
                    json.dumps(conversation.data, sort_keys=True),
                    to_iso(now),
                ),
            )
        return Conversation(
            conversation.channel,
            conversation.chat_id,
            conversation.actor,
            conversation.state,
            dict(conversation.data),
            now,
        )

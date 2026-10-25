"""Inti percakapan (sinkron, tanpa aiogram): pesan/tombol → Studio Controller → layar.

Engine tidak menyimpan state di memori: konteks percakapan ada di SQLite
(`ConversationStore`), jadi bot yang di-restart melanjutkan dari tempat yang sama.
Engine hanya memanggil `StudioController`; tidak ada akses langsung ke modul domain.
"""

from __future__ import annotations

import html
import re
from dataclasses import replace
from typing import Any

from studio.interfaces.telegram import render, texts
from studio.interfaces.telegram.callbacks import Callback, CallbackError, button, decode
from studio.interfaces.telegram.intents import (
    Intent,
    IntentName,
    IntentParser,
    RuleBasedIntentParser,
)
from studio.interfaces.telegram.types import AnswerCallback, Inbound, Reply, Screen
from studio.modules.approvals import ApprovalExpiredError
from studio.modules.artifacts import ArtifactKind
from studio.modules.controller import (
    IDLE,
    ActionReply,
    Conversation,
    ConversationStore,
    EpisodeFilter,
    NotReadyError,
    Outcome,
    StudioController,
)
from studio.modules.episodes import Category, DocumentaryFormat, EpisodeStatus
from studio.modules.notifications import Notification, NotificationKind
from studio.shared.actors import Actor
from studio.shared.errors import NotAuthorizedError, NotFoundError, StudioError
from studio.shared.gates import Gate

CHANNEL = "telegram"

# State percakapan
CREATE = "create"
AWAITING_REVISION_NOTES = "awaiting_revision_notes"  # setelah memilih target revisi di kartu
AWAITING_SCRIPT_NOTES = "awaiting_script_notes"  # setelah "✏️ Minta revisi" di layar naskah

COMMANDS = {"/start", "/help", "/menu", "/status", "/episodes", "/budget", "/cancel"}


def _friendly(exc: Exception) -> str:
    message = str(exc).strip() or "Permintaan tidak bisa diproses."
    return "⚠️ " + render.esc(message[0].upper() + message[1:])


class ConversationEngine:
    def __init__(
        self,
        controller: StudioController,
        conversations: ConversationStore,
        parser: IntentParser | None = None,
    ) -> None:
        self._c = controller
        self._conversations = conversations
        self._parser = parser or RuleBasedIntentParser(controller.scripting)

    # --- titik masuk -------------------------------------------------------------

    def handle(self, inbound: Inbound, actor: Actor) -> Reply:
        reply = Reply()
        conv = self._conversations.get(CHANNEL, str(inbound.chat_id), actor.label)
        try:
            if inbound.is_callback:
                self._on_callback(inbound, actor, conv, reply)
            else:
                self._on_message(inbound, actor, conv, reply)
        except NotAuthorizedError:
            self._say(inbound, reply, Screen(texts.NOT_OWNER), alert=True)
        except (NotFoundError, NotReadyError, CallbackError, StudioError) as exc:
            self._say(
                inbound, reply, Screen(_friendly(exc), render.rows(render.menu_row())), alert=True
            )
        return reply

    def _say(self, inbound: Inbound, reply: Reply, screen: Screen, *, alert: bool = False) -> None:
        if inbound.callback_id is not None:
            reply.answer(inbound.callback_id, render.clip(_plain(screen.text), 190), alert=alert)
        else:
            reply.send(inbound.chat_id, screen)

    def _show(self, inbound: Inbound, reply: Reply, screen: Screen) -> None:
        """Tampilkan layar: edit pesan tombol yang ditekan (navigasi), atau kirim baru."""
        if inbound.callback_id is not None and inbound.message_id is not None:
            reply.edit(inbound.chat_id, inbound.message_id, screen)
        else:
            reply.send(inbound.chat_id, screen)

    def _save(self, conv: Conversation, state: str = IDLE, **data: Any) -> Conversation:
        merged = {k: v for k, v in conv.data.items() if k == "episode_id"}
        merged.update({k: v for k, v in data.items() if v is not None})
        return self._conversations.save(replace(conv, state=state, data=merged))

    def _focus(self, conv: Conversation, episode_id: str) -> Conversation:
        data = dict(conv.data)
        data["episode_id"] = episode_id
        return self._conversations.save(replace(conv, data=data))

    # --- pesan teks ------------------------------------------------------------------

    def _on_message(self, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply) -> None:
        text = (inbound.text or "").strip()
        if text.startswith("/"):
            self._on_command(text.split()[0].split("@")[0].lower(), inbound, actor, conv, reply)
            return
        intent = self._parser.parse(text)
        if conv.state in (AWAITING_REVISION_NOTES, AWAITING_SCRIPT_NOTES):
            if intent.name is IntentName.CANCEL_STEP:
                self._save(conv)
                reply.send(inbound.chat_id, render.main_menu(texts.STEP_CANCELLED))
                return
            self._on_notes(text, inbound, actor, conv, reply)
            return
        if conv.state == CREATE and intent.name in (
            IntentName.SET_FORMAT,
            IntentName.SET_CATEGORY,
            IntentName.CREATE,
            IntentName.UNKNOWN,
        ):
            self._continue_create(intent, inbound, actor, conv, reply)
            return
        self._on_intent(intent, inbound, actor, conv, reply)

    def _on_command(
        self, command: str, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        if command in ("/start", "/menu"):
            self._save(conv)
            reply.send(inbound.chat_id, render.main_menu())
        elif command == "/help":
            reply.send(inbound.chat_id, render.help_screen())
        elif command == "/status":
            reply.send(inbound.chat_id, render.production_screen(self._c.production_status(actor)))
        elif command == "/episodes":
            page = self._c.list_episodes(actor, EpisodeFilter.ACTIVE, per_page=render.PER_PAGE)
            reply.send(inbound.chat_id, render.episode_list(page, EpisodeFilter.ACTIVE))
        elif command == "/budget":
            reply.send(inbound.chat_id, render.budget_screen(self._c.budget_dashboard(actor)))
        elif command == "/cancel":
            self._save(conv)
            reply.send(inbound.chat_id, render.main_menu(texts.STEP_CANCELLED))
        else:
            reply.send(inbound.chat_id, render.main_menu(texts.UNKNOWN))

    def _on_notes(
        self, text: str, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        if conv.state == AWAITING_REVISION_NOTES:
            self._save(conv)
            result = self._c.submit_notes(actor, str(conv.data["action_id"]), text)
            self._after_action(result, inbound, actor, conv, reply)
            return
        episode_id = str(conv.data["revise_episode_id"])
        self._save(conv)
        card = self._c.confirm_script_revision(actor, episode_id, text)
        reply.send(inbound.chat_id, render.confirm_card(card, "Kirim revisi naskah?"))

    def _on_intent(
        self, intent: Intent, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        chat = inbound.chat_id
        match intent.name:
            case IntentName.HELP:
                reply.send(chat, render.help_screen())
            case IntentName.MENU:
                reply.send(chat, render.main_menu())
            case IntentName.CANCEL_STEP:
                self._save(conv)
                reply.send(chat, render.main_menu(texts.STEP_CANCELLED))
            case IntentName.CREATE | IntentName.SET_FORMAT | IntentName.SET_CATEGORY:
                self._continue_create(intent, inbound, actor, replace(conv, data={}), reply)
            case IntentName.BUDGET:
                reply.send(chat, render.budget_screen(self._c.budget_dashboard(actor)))
            case IntentName.LIST_PENDING:
                reply.send(chat, render.pending_list(self._c.pending_approvals(actor)))
            case IntentName.DECISION_BY_TEXT:
                pending = self._c.pending_approvals(actor)
                screen = render.pending_list(pending)
                reply.send(
                    chat, Screen(texts.DECISION_BY_TEXT + "\n\n" + screen.text, screen.keyboard)
                )
            case IntentName.LIST_EPISODES:
                page = self._c.list_episodes(actor, EpisodeFilter.ACTIVE, per_page=render.PER_PAGE)
                reply.send(chat, render.episode_list(page, EpisodeFilter.ACTIVE))
            case IntentName.STATUS:
                reply.send(chat, render.production_screen(self._c.production_status(actor)))
            case IntentName.SHOW_RESEARCH | IntentName.CLAIM_SOURCES:
                episode_id = self._resolve(
                    intent, actor, conv, ArtifactKind.FACTCHECK, "r", reply, chat
                )
                if episode_id is None:
                    return
                conv = self._focus(conv, episode_id)
                view = self._c.research(actor, episode_id)
                if intent.name is IntentName.SHOW_RESEARCH:
                    reply.send(chat, render.research_screen(view))
                elif intent.claim_id:
                    claims = view.brief.all_claims()
                    index = next(
                        (
                            i
                            for i, c in enumerate(claims)
                            if c.id.lower() == intent.claim_id.lower()
                        ),
                        None,
                    )
                    if index is None:
                        reply.send(chat, render.claim_picker(view))
                    else:
                        cs = self._c.claim_sources(actor, episode_id, claims[index].id)
                        reply.send(chat, render.claim_sources(cs, index))
                else:
                    reply.send(chat, render.claim_picker(view))
            case IntentName.SHOW_SCRIPT | IntentName.SHOW_SEGMENT:
                episode_id = self._resolve(
                    intent, actor, conv, ArtifactKind.SCRIPT, "s", reply, chat
                )
                if episode_id is None:
                    return
                self._focus(conv, episode_id)
                script_view = self._c.script(actor, episode_id)
                segment = "o"
                if intent.segment is not None:
                    roles = [s.role for s in script_view.script.segments]
                    segment = str(roles.index(intent.segment)) if intent.segment in roles else "o"
                reply.send(chat, render.script_screen(script_view, segment))
            case IntentName.REVISE_SCRIPT:
                episode_id = self._resolve(
                    intent, actor, conv, ArtifactKind.SCRIPT, "s", reply, chat
                )
                if episode_id is None:
                    return
                self._focus(conv, episode_id)
                card = self._c.confirm_script_revision(actor, episode_id, intent.notes or "")
                reply.send(chat, render.confirm_card(card, "Kirim revisi naskah?"))
            case IntentName.EPISODE_COST:
                episode_id = self._resolve(intent, actor, conv, None, "e", reply, chat)
                if episode_id is None:
                    return
                self._focus(conv, episode_id)
                reply.send(chat, render.cost_screen(self._c.episode_cost(actor, episode_id)))
            case _:
                reply.send(chat, render.main_menu(texts.UNKNOWN))

    def _resolve(
        self,
        intent: Intent,
        actor: Actor,
        conv: Conversation,
        needs: ArtifactKind | None,
        purpose: str,
        reply: Reply,
        chat: int,
    ) -> str | None:
        """Tentukan episode yang dimaksud. Kalau ragu, TANYA (tidak menebak)."""
        if intent.episode_ref:
            found = self._c.find_episodes(actor, intent.episode_ref)
            if len(found) == 1:
                return found[0].id
            if not found:
                reply.send(
                    chat, Screen(f"Episode {render.esc(intent.episode_ref)} tidak ditemukan.")
                )
                return None
        elif conv.current_episode_id:
            return conv.current_episode_id
        page = self._c.list_episodes(
            actor, EpisodeFilter.ACTIVE, per_page=render.PER_PAGE, with_artifact=needs
        )
        if page.total == 1:
            return page.items[0].episode.id
        if page.total == 0:
            what = {ArtifactKind.FACTCHECK: "riset", ArtifactKind.SCRIPT: "naskah"}.get(
                needs or ArtifactKind.TOPICS, ""
            )
            reply.send(
                chat,
                render.main_menu(f"Belum ada episode aktif{' dengan ' + what if what else ''}."),
            )
            return None
        reply.send(
            chat,
            render.episode_list(
                page, EpisodeFilter.ACTIVE, purpose=purpose, title=texts.ASK_EPISODE
            ),
        )
        return None

    # --- alur buat dokumenter ----------------------------------------------------------

    def _continue_create(
        self, intent: Intent, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        data = dict(conv.data) if conv.state == CREATE else {}
        notes: list[str] = []
        if intent.format is not None:
            data["format"] = intent.format.value
        if intent.duration_s is not None:
            data["duration"] = intent.duration_s
        if intent.category is not None:
            data["category"] = intent.category.value
        if intent.topic:
            data["idea"] = intent.topic
        if "duration" in intent.ambiguities:
            data.pop("format", None)
            data.pop("duration", None)
            notes.append(
                "Durasi itu tidak cocok dengan format mana pun (Quick 30–45, Archives 75–90, "
                "Deep 120–180 detik)."
            )
        if "format" in intent.ambiguities:
            notes.append("Saya menangkap lebih dari satu format.")
        if "category" in intent.ambiguities:
            notes.append("Saya menangkap lebih dari satu kategori.")
        if intent.name is IntentName.UNKNOWN and not notes:
            notes.append("Belum paham pilihan itu.")
        self._advance_create(data, inbound, actor, conv, reply, " ".join(notes))

    def _advance_create(
        self,
        data: dict[str, Any],
        inbound: Inbound,
        actor: Actor,
        conv: Conversation,
        reply: Reply,
        note: str = "",
    ) -> None:
        prefix = (note + "\n") if note else ""
        summary = self._create_summary(data)
        if summary:
            prefix += summary + "\n"
        if "format" not in data:
            self._save(conv, CREATE, **data)
            screen = render.ask_format()
            self._show(inbound, reply, Screen(prefix + screen.text, screen.keyboard))
            return
        if "category" not in data:
            self._save(conv, CREATE, **data)
            screen = render.ask_category()
            self._show(inbound, reply, Screen(prefix + screen.text, screen.keyboard))
            return
        self._save(conv)
        card = self._c.confirm_create(
            actor,
            format=DocumentaryFormat(data["format"]),
            category=Category(data["category"]),
            idea=data.get("idea"),
            target_duration_s=data.get("duration"),
        )
        screen = render.confirm_card(card, "Buat dokumenter ini?")
        self._show(inbound, reply, Screen(screen.text, screen.keyboard))

    @staticmethod
    def _create_summary(data: dict[str, Any]) -> str:
        parts = []
        if "format" in data:
            parts.append(texts.FORMAT_BUTTON[DocumentaryFormat(data["format"])])
        if "duration" in data:
            parts.append(f"{data['duration']} detik")
        if "category" in data:
            parts.append(texts.CATEGORY_BUTTON[Category(data["category"])])
        if "idea" in data:
            parts.append(f"ide: {render.esc(render.clip(str(data['idea']), 80))}")
        return ("🎬 " + " · ".join(parts)) if parts else ""

    # --- tombol ------------------------------------------------------------------------

    def _on_callback(
        self, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        callback_id = inbound.callback_id or ""
        cb = decode(inbound.callback_data or "")
        handler = {
            "m": self._cb_menu,
            "l": self._cb_list,
            "e": self._cb_episode,
            "t": self._cb_topics,
            "r": self._cb_research,
            "c": self._cb_claim,
            "s": self._cb_script,
            "$": self._cb_cost,
            "ap": self._cb_approval,
            "pa": self._cb_pending,
            "n": self._cb_new,
            "q": self._cb_confirm,
            "a": self._cb_action,
        }.get(cb.kind)
        if handler is None:
            raise CallbackError("tombol tidak dikenal")
        before = len(reply.actions)
        handler(cb, inbound, actor, conv, reply)
        if not any(getattr(a, "callback_id", None) == callback_id for a in reply.actions[before:]):
            reply.actions.insert(before, _answer(callback_id))

    def _cb_menu(
        self, cb: Callback, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        key = cb.part(0, "main")
        if key == "main":
            self._save(conv)
            self._show(inbound, reply, render.main_menu("🏠 <b>Menu utama</b>"))
        elif key == "new":
            self._advance_create({}, inbound, actor, replace(conv, data={}), reply)
        elif key == "eps":
            page = self._c.list_episodes(actor, EpisodeFilter.ACTIVE, per_page=render.PER_PAGE)
            self._show(inbound, reply, render.episode_list(page, EpisodeFilter.ACTIVE))
        elif key == "ideas":
            page = self._c.list_episodes(
                actor, EpisodeFilter.AWAITING, per_page=render.PER_PAGE, gate=Gate.TOPIC
            )
            screen = render.episode_list(
                page, EpisodeFilter.AWAITING, title="💡 <b>Kandidat topik menunggu pilihan Anda</b>"
            )
            if page.total == 0:
                screen = Screen(
                    "💡 Belum ada kandidat topik yang menunggu. Mulai cari ide baru?",
                    render.rows([button("🔎 Cari ide topik baru", "m", "new")], render.menu_row()),
                )
            self._show(inbound, reply, screen)
        elif key == "research":
            page = self._c.list_episodes(
                actor,
                EpisodeFilter.ALL,
                per_page=render.PER_PAGE,
                with_artifact=ArtifactKind.FACTCHECK,
            )
            self._show(
                inbound,
                reply,
                render.episode_list(
                    page, EpisodeFilter.ALL, purpose="r", title="🔎 <b>Review riset</b>"
                ),
            )
        elif key == "script":
            page = self._c.list_episodes(
                actor,
                EpisodeFilter.ALL,
                per_page=render.PER_PAGE,
                with_artifact=ArtifactKind.SCRIPT,
            )
            self._show(
                inbound,
                reply,
                render.episode_list(
                    page, EpisodeFilter.ALL, purpose="s", title="📝 <b>Review naskah</b>"
                ),
            )
        elif key == "appr":
            self._show(inbound, reply, render.pending_list(self._c.pending_approvals(actor)))
        elif key == "status":
            self._show(inbound, reply, render.production_screen(self._c.production_status(actor)))
        elif key == "budget":
            self._show(inbound, reply, render.budget_screen(self._c.budget_dashboard(actor)))
        elif key == "settings":
            self._show(inbound, reply, render.settings_screen(self._c.settings_view(actor)))
        else:
            self._show(inbound, reply, render.help_screen())

    def _cb_list(
        self, cb: Callback, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        try:
            flt = EpisodeFilter(cb.part(0, "active"))
        except ValueError as exc:
            raise CallbackError("filter tidak dikenal") from exc
        purpose = cb.part(1, "e")
        needs = {"r": ArtifactKind.FACTCHECK, "s": ArtifactKind.SCRIPT}.get(purpose)
        page = self._c.list_episodes(
            actor, flt, page=cb.number(2), per_page=render.PER_PAGE, with_artifact=needs
        )
        self._show(inbound, reply, render.episode_list(page, flt, purpose=purpose))

    def _cb_episode(
        self, cb: Callback, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        episode_id = cb.part(0)
        self._focus(conv, episode_id)
        self._show(inbound, reply, render.episode_detail(self._c.episode_detail(actor, episode_id)))

    def _cb_topics(
        self, cb: Callback, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        episode_id = cb.part(0)
        self._focus(conv, episode_id)
        episode = self._c.episode(actor, episode_id)
        self._show(inbound, reply, render.topics_screen(episode, self._c.topics(actor, episode_id)))

    def _cb_research(
        self, cb: Callback, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        episode_id = cb.part(0)
        self._focus(conv, episode_id)
        view = self._c.research(actor, episode_id)
        self._show(inbound, reply, render.research_screen(view, cb.part(1, "sum"), cb.number(2)))

    def _cb_claim(
        self, cb: Callback, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        episode_id, index = cb.part(0), cb.number(1, -1)
        claims = self._c.research(actor, episode_id).brief.all_claims()
        if not 0 <= index < len(claims):
            raise CallbackError("klaim tidak ditemukan; buka ulang ringkasan riset")
        cs = self._c.claim_sources(actor, episode_id, claims[index].id)
        self._show(inbound, reply, render.claim_sources(cs, index))

    def _cb_script(
        self, cb: Callback, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        episode_id = cb.part(0)
        self._focus(conv, episode_id)
        self._show(
            inbound, reply, render.script_screen(self._c.script(actor, episode_id), cb.part(1, "o"))
        )

    def _cb_cost(
        self, cb: Callback, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        episode_id = cb.part(0)
        self._focus(conv, episode_id)
        self._show(inbound, reply, render.cost_screen(self._c.episode_cost(actor, episode_id)))

    def _cb_pending(
        self, cb: Callback, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        self._show(
            inbound, reply, render.pending_list(self._c.pending_approvals(actor), cb.number(0))
        )

    def _cb_approval(
        self, cb: Callback, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        try:
            card = self._c.approval_card(actor, cb.part(0))
        except ApprovalExpiredError:
            approval = next(
                (
                    a.approval
                    for a in self._c.pending_approvals(actor)
                    if a.approval.id == cb.part(0)
                ),
                None,
            )
            if approval is None:
                raise
            self._show(inbound, reply, Screen("⌛ Approval ini sudah kedaluwarsa."))
            confirm = self._c.confirm_reissue(actor, approval.episode_id)
            reply.send(inbound.chat_id, render.confirm_card(confirm, "Terbitkan ulang approval?"))
            return
        self._focus(conv, card.episode.id)
        self._show(inbound, reply, render.approval_card(card))

    def _cb_new(
        self, cb: Callback, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        step = cb.part(0)
        if step == "x":
            self._save(conv)
            self._show(inbound, reply, render.main_menu(texts.STEP_CANCELLED))
            return
        data = dict(conv.data) if conv.state == CREATE else {}
        try:
            if step == "f":
                data["format"] = DocumentaryFormat(cb.part(1)).value
                data.pop("duration", None)
            elif step == "c":
                data["category"] = Category(cb.part(1)).value
            else:
                raise CallbackError("langkah tidak dikenal")
        except ValueError as exc:
            raise CallbackError("pilihan tidak dikenal") from exc
        self._advance_create(data, inbound, actor, conv, reply)

    def _cb_confirm(
        self, cb: Callback, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        what, episode_id = cb.part(0), cb.part(1)
        if what == "retry":
            card = self._c.confirm_retry(actor, episode_id)
            reply.send(inbound.chat_id, render.confirm_card(card, "Ulangi tahap yang gagal?"))
        elif what == "cancel":
            card = self._c.confirm_cancel(actor, episode_id)
            reply.send(inbound.chat_id, render.confirm_card(card, "Batalkan episode?"))
        elif what == "reissue":
            card = self._c.confirm_reissue(actor, episode_id)
            reply.send(inbound.chat_id, render.confirm_card(card, "Terbitkan ulang approval?"))
        elif what == "budget":
            card = self._c.confirm_activate_budget(actor)
            reply.send(inbound.chat_id, render.confirm_card(card, "Aktifkan periode anggaran?"))
        elif what == "revise":
            self._c.episode(actor, episode_id)  # cek owner + episode ada
            self._save(
                conv, AWAITING_SCRIPT_NOTES, revise_episode_id=episode_id, episode_id=episode_id
            )
            reply.send(inbound.chat_id, Screen(texts.ASK_REVISION_NOTES))
        else:
            raise CallbackError("konfirmasi tidak dikenal")

    def _cb_action(
        self, cb: Callback, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        result = self._c.press(actor, cb.part(0))
        self._after_action(result, inbound, actor, conv, reply)

    # --- hasil aksi ------------------------------------------------------------------

    def _after_action(
        self, result: ActionReply, inbound: Inbound, actor: Actor, conv: Conversation, reply: Reply
    ) -> None:
        chat, message_id = inbound.chat_id, inbound.message_id
        if result.outcome in (Outcome.REFUSED, Outcome.FAILED):
            if inbound.callback_id is not None:
                reply.answer(inbound.callback_id, render.clip(result.message, 190), alert=True)
                if result.outcome is Outcome.REFUSED and message_id is not None:
                    reply.clear_keyboard(chat, message_id)
            else:
                reply.send(
                    chat, Screen("⚠️ " + render.esc(result.message), render.rows(render.menu_row()))
                )
            return
        if result.episode is not None:
            conv = self._focus(conv, result.episode.id)

        if result.outcome is Outcome.REVISE_MENU and result.revise is not None:
            self._show(inbound, reply, render.revise_card(result.revise))
            return
        if result.outcome is Outcome.NEEDS_NOTES and result.pending_action_id:
            self._save(
                conv,
                AWAITING_REVISION_NOTES,
                action_id=result.pending_action_id,
                episode_id=result.episode.id if result.episode else None,
            )
            target = EpisodeStatus(result.revise_to) if result.revise_to else None
            label = texts.REVISION_TARGET_LABEL.get(target, "") if target else ""
            self._show(inbound, reply, Screen(f"✏️ <b>{label}</b>\n{texts.ASK_REVISION_NOTES}"))
            return
        if result.outcome is Outcome.DISMISSED:
            self._show(inbound, reply, Screen("Dibatalkan.", render.rows(render.menu_row())))
            return
        if result.outcome is Outcome.EXPIRED and result.episode is not None:
            self._show(inbound, reply, Screen("⌛ " + render.esc(result.message)))
            confirm = self._c.confirm_reissue(actor, result.episode.id)
            reply.send(chat, render.confirm_card(confirm, "Terbitkan ulang approval?"))
            return
        if result.outcome is Outcome.STALE:
            self._show(inbound, reply, Screen("♻️ " + render.esc(result.message)))
            if result.approval is not None:
                card = self._c.approval_card(actor, result.approval.id)
                reply.send(
                    chat, render.approval_card(card, "🆕 Kartu pengganti dengan konten terbaru:")
                )
            return
        if result.approval is not None:
            card = self._c.approval_card(actor, result.approval.id)
            self._show(inbound, reply, render.approval_card(card))
            return
        follow: list[Any] = [render.menu_row()]
        if result.episode is not None:
            follow.insert(0, [button("📁 Episode", "e", result.episode.id)])
        self._show(inbound, reply, Screen("✅ " + render.esc(result.message), render.rows(*follow)))

    # --- notifikasi ---------------------------------------------------------------------

    def render_notification(self, notification: Notification, actor: Actor) -> Screen | None:
        """Layar untuk satu notifikasi, atau None kalau sudah tidak relevan (misalnya approval
        sudah diputuskan sebelum notifikasinya terkirim)."""
        kind = notification.kind
        episode_id = notification.episode_id
        if episode_id is None:
            return None
        try:
            episode = self._c.episode(actor, episode_id)
        except NotFoundError:
            return None
        name = render.esc(render.episode_name(episode))
        tag = render.short_id(episode.id)
        episode_row = [button("📁 Episode", "e", episode.id)]
        if kind is NotificationKind.APPROVAL_REQUESTED:
            approval_id = notification.ref_id or ""
            try:
                card = self._c.approval_card(actor, approval_id)
            except StudioError:
                return None  # sudah diputuskan / digantikan
            header = {
                Gate.TOPIC: "💡 <b>Topik siap dipilih.</b> G0 menunggu approval Anda.",
                Gate.EDITORIAL: "📝 <b>Naskah siap direview.</b> G1 menunggu approval Anda.",
                Gate.COST: "💸 G2 menunggu approval (simulasi).",
                Gate.FINAL: "🎞 G3 menunggu approval (simulasi).",
            }[card.approval.gate]
            return render.approval_card(card, header)
        if kind is NotificationKind.RESEARCH_STARTED:
            return Screen(f"🔎 Riset dimulai — <b>{name}</b> {tag}", render.rows(episode_row))
        if kind is NotificationKind.RESEARCH_BRIEF_READY:
            try:
                view = self._c.research(actor, episode.id)
                facts = f"{view.report.verified_facts} fakta terverifikasi"
            except NotReadyError:
                facts = "brief tersimpan"
            return Screen(
                f"✅ ResearchBrief selesai — <b>{name}</b> {tag}\n{facts}. Naskah sedang ditulis…",
                render.rows([button("🔎 Lihat riset", "r", episode.id, "sum", 0)], episode_row),
            )
        if kind is NotificationKind.SCRIPT_READY:
            try:
                script = self._c.script(actor, episode.id).script
                info = f"{script.estimated_duration_s:.1f} dtk · {script.word_count} kata"
            except NotReadyError:
                info = "naskah tersimpan"
            return Screen(
                f"📝 Naskah selesai — <b>{name}</b> {tag}\n{info}. Menyiapkan kartu G1…",
                render.rows([button("📝 Lihat naskah", "s", episode.id, "o")], episode_row),
            )
        if kind is NotificationKind.EPISODE_FAILED:
            reason = render.esc(render.clip(str(notification.data.get("reason") or "-"), 300))
            stage = render.esc(str(notification.data.get("from", "-")))
            actions = [button("🔁 Ulangi", "q", "retry", episode.id)]
            if notification.data.get("from") == EpisodeStatus.SCRIPTING.value:
                actions.append(button("✏️ Revisi naskah", "q", "revise", episode.id))
            return Screen(
                f"❗ Episode gagal di tahap {stage} — <b>{name}</b> {tag}\n{reason}",
                render.rows(actions, episode_row),
            )
        if kind is NotificationKind.JOB_RETRY:
            data = notification.data
            stage = render.esc(str(data.get("stage", "-")))
            return Screen(
                f"⏳ Tahap {stage} gagal sementara — <b>{name}</b> "
                f"{tag}\nDicoba lagi otomatis (percobaan {data.get('attempts')}/"
                f"{data.get('max_attempts')}).",
                render.rows(episode_row),
            )
        if kind is NotificationKind.EPISODE_COMPLETED:
            return Screen(
                f"🎉 Episode selesai (ekspor simulasi) — <b>{name}</b> {tag}",
                render.rows(episode_row),
            )
        to = render.esc(str(notification.data.get("to", "")))
        return Screen(f"📁 Episode ditutup ({to}) — <b>{name}</b> {tag}", render.rows(episode_row))


def _answer(callback_id: str) -> AnswerCallback:
    return AnswerCallback(callback_id)


def _plain(text: str) -> str:
    """Teks tanpa tag HTML untuk notifikasi pop-up tombol (tidak mendukung format)."""
    return html.unescape(re.sub(r"<[^>]+>", "", text))

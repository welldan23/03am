"""Render read model controller → layar Telegram (HTML) + inline keyboard.

Semua nilai dinamis di-escape. Tag HTML hanya dipakai dalam satu baris, jadi pesan aman
dipecah per baris kalau melebihi batas 4096 karakter Telegram.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from decimal import Decimal

from studio.interfaces.telegram import texts
from studio.interfaces.telegram.callbacks import action, button
from studio.interfaces.telegram.types import MAX_MESSAGE_CHARS, Button, Keyboard, Screen
from studio.modules.approvals import Approval
from studio.modules.controller import (
    ApprovalCard,
    ApprovalSummary,
    BudgetDashboard,
    ClaimSources,
    ConfirmCard,
    EpisodeCost,
    EpisodeDetail,
    EpisodeFilter,
    EpisodeSummary,
    Page,
    ProductionItem,
    ResearchView,
    ReviseCard,
    ScriptView,
    StudioSettingsView,
)
from studio.modules.episodes import Category, DocumentaryFormat, Episode, EpisodeStatus, state
from studio.modules.research import CATEGORY_LABEL, ClaimCategory, ClaimRecord, TopicCandidate
from studio.shared.gates import Gate
from studio.shared.money import format_idr

PER_PAGE = 4
SOURCES_PER_PAGE = 4
CLAIMS_PER_PAGE = 6

esc = html.escape


def clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def short_id(episode_id: str) -> str:
    return "#" + episode_id[-6:]


def fx_text(value: str) -> str:
    amount = Decimal(value)
    if amount == amount.to_integral_value():
        return f"{int(amount):,}".replace(",", ".")
    return value


def split_text(text: str, limit: int = MAX_MESSAGE_CHARS) -> list[str]:
    """Pecah teks di batas baris supaya tiap potongan ≤ `limit` karakter."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:  # baris tunggal yang sangat panjang (jarang): potong keras
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def rows(*items: Sequence[Button]) -> Keyboard:
    return tuple(tuple(row) for row in items if row)


def grid(buttons: Sequence[Button], width: int = 2) -> list[list[Button]]:
    return [list(buttons[i : i + width]) for i in range(0, len(buttons), width)]


def pager(kind: str, prefix: Sequence[str | int], page: int, pages: int) -> list[Button]:
    if pages <= 1:
        return []
    nav: list[Button] = []
    if page > 0:
        nav.append(button("◀️", kind, *prefix, page - 1))
    nav.append(button(f"{page + 1}/{pages}", kind, *prefix, page))
    if page < pages - 1:
        nav.append(button("▶️", kind, *prefix, page + 1))
    return nav


def menu_row() -> list[Button]:
    return [button("🏠 Menu", "m", "main")]


def episode_name(episode: Episode) -> str:
    return clip(episode.title or episode.idea or "(belum berjudul)", 48)


# --- menu ------------------------------------------------------------------------


def main_menu(text: str = texts.WELCOME) -> Screen:
    buttons = [button(label, "m", key) for label, key in texts.MENU_ITEMS]
    return Screen(text, rows(*grid(buttons)))


def help_screen() -> Screen:
    return Screen(texts.HELP, rows(menu_row()))


def ask_format() -> Screen:
    return Screen(
        texts.ASK_FORMAT,
        rows(
            *[[button(texts.FORMAT_BUTTON[f], "n", "f", f.value)] for f in DocumentaryFormat],
            [button("Batal", "n", "x")],
        ),
    )


def ask_category(prefix: str = "") -> Screen:
    buttons = [button(texts.CATEGORY_BUTTON[c], "n", "c", c.value) for c in Category]
    return Screen(
        (prefix + "\n" if prefix else "") + texts.ASK_CATEGORY,
        rows(*grid(buttons), [button("Batal", "n", "x")]),
    )


# --- episode ---------------------------------------------------------------------


def _status_line(episode: Episode) -> str:
    return texts.STATUS_LABEL[episode.status]


def episode_list(
    page: Page[EpisodeSummary], flt: EpisodeFilter, *, purpose: str = "e", title: str = ""
) -> Screen:
    if page.total == 0:
        return Screen(
            texts.NO_EPISODES, rows([button("🎬 Buat Dokumenter", "m", "new")], menu_row())
        )
    header = (
        title
        or {
            EpisodeFilter.ACTIVE: "📂 <b>Episode aktif</b>",
            EpisodeFilter.AWAITING: "⏳ <b>Menunggu keputusan Anda</b>",
            EpisodeFilter.WORKING: "⚙️ <b>Sedang diproses</b>",
            EpisodeFilter.ALL: "🗃 <b>Semua episode</b>",
        }[flt]
    )
    lines = [f"{header} ({page.total})"]
    buttons = []
    for item in page.items:
        ep = item.episode
        gate = f" · ⏳ {item.pending.gate.value}" if item.pending else ""
        lines.append(
            f"• <b>{esc(episode_name(ep))}</b> {short_id(ep.id)}\n  {_status_line(ep)}{gate}"
        )
        target = {"r": "r", "s": "s"}.get(purpose)
        if target == "r":
            buttons.append([button(f"🔎 {clip(episode_name(ep), 30)}", "r", ep.id, "sum", 0)])
        elif target == "s":
            buttons.append([button(f"📝 {clip(episode_name(ep), 30)}", "s", ep.id, "o")])
        else:
            buttons.append([button(f"📁 {clip(episode_name(ep), 30)}", "e", ep.id)])
    nav = pager("l", [flt.value, purpose], page.page, page.pages)  # l:<filter>:<purpose>:<page>
    return Screen("\n".join(lines), rows(*buttons, nav, menu_row()))


def episode_detail(detail: EpisodeDetail) -> Screen:
    ep = detail.episode
    fmt = ep.format.value if ep.format else "otomatis"
    lines = [
        f"📁 <b>{esc(episode_name(ep))}</b>",
        f"ID {short_id(ep.id)} · {ep.category.value} · {fmt} · target {ep.target_duration_s} dtk",
        f"Status: {_status_line(ep)} (versi {ep.version})",
    ]
    if ep.status is EpisodeStatus.FAILED:
        where = ep.failed_from.value if ep.failed_from else "-"
        lines.append(f"❗ Gagal di {where}: {esc(clip(ep.failure_reason or '-', 300))}")
    for approval in detail.pending:
        lines.append(f"⏳ Menunggu {texts.GATE_LABEL[approval.gate]}")
    lines.append(
        f"Biaya: {format_idr(detail.spent_simulated_idr)} (simulasi) · "
        f"{format_idr(detail.spent_real_idr)} (real)"
    )
    kinds = set(detail.artifact_kinds)
    first: list[Button] = []
    if "factcheck" in kinds:
        first.append(button("🔎 Riset", "r", ep.id, "sum", 0))
    if "script" in kinds:
        first.append(button("📝 Naskah", "s", ep.id, "o"))
    first.append(button("💸 Biaya", "$", ep.id))
    second: list[Button] = [button(f"✅ {a.gate.value}", "ap", a.id) for a in detail.pending]
    if "topics" in kinds:
        second.append(button("💡 Topik", "t", ep.id))
    third: list[Button] = []
    if ep.status is EpisodeStatus.FAILED:
        third.append(button("🔁 Ulangi", "q", "retry", ep.id))
        if ep.failed_from is EpisodeStatus.SCRIPTING:
            third.append(button("✏️ Revisi naskah", "q", "revise", ep.id))
    if ep.status is EpisodeStatus.AWAITING_EDITORIAL:
        third.append(button("✏️ Revisi naskah", "q", "revise", ep.id))
    if ep.status not in state.TERMINAL:
        third.append(button("🛑 Batalkan", "q", "cancel", ep.id))
    return Screen("\n".join(lines), rows(first, second, third, menu_row()))


def topics_screen(episode: Episode, topics: list[TopicCandidate]) -> Screen:
    lines = [f"💡 <b>Kandidat topik</b> — {short_id(episode.id)}"]
    for number, topic in enumerate(topics, start=1):
        lines.append(_topic_block(number, topic))
    return Screen("\n\n".join(lines), rows([button("📁 Episode", "e", episode.id)], menu_row()))


def _topic_block(number: int, topic: TopicCandidate) -> str:
    return (
        f"<b>{number}. {esc(topic.title)}</b>\n"
        f"{esc(topic.topic_category.value)} · sensitivitas {topic.sensitivity.value} · "
        f"keterverifikasian {topic.verifiability.value}\n"
        f"<i>{esc(clip(topic.hook_question, 160))}</i>"
    )


# --- riset -----------------------------------------------------------------------

RESEARCH_SECTIONS: dict[str, tuple[str, tuple[ClaimCategory, ...]]] = {
    "fact": ("✅ Fakta terverifikasi", (ClaimCategory.VERIFIED_FACT,)),
    "disp": ("⚖️ Diperdebatkan", (ClaimCategory.DISPUTED,)),
    "unv": ("❔ Belum terverifikasi", (ClaimCategory.UNVERIFIED,)),
    "intp": (
        "💭 Interpretasi & hipotesis",
        (ClaimCategory.INTERPRETATION, ClaimCategory.HYPOTHESIS),
    ),
}


def _claims_of(view: ResearchView, categories: tuple[ClaimCategory, ...]) -> list[ClaimRecord]:
    return [c for c in view.brief.all_claims() if c.category in categories]


def research_screen(view: ResearchView, section: str = "sum", page: int = 0) -> Screen:
    ep = view.episode
    if section in RESEARCH_SECTIONS:
        return _research_claims(view, section, page)
    if section == "src":
        return _research_sources(view, page)
    if section == "warn":
        return _research_warnings(view, page)
    if section == "clm":
        return claim_picker(view, page)
    brief, report = view.brief, view.report
    tiers = ", ".join(f"tier {k}: {v}" for k, v in sorted(report.sources_by_tier.items()))
    quarantined = sum(1 for s in brief.sources if s.quarantined)
    flagged = sum(1 for i in report.issues if i.severity.value != "info")
    counts = " · ".join(
        f"{len(_claims_of(view, cats))} {label.split(' ', 1)[1].lower()}"
        for label, cats in RESEARCH_SECTIONS.values()
    )
    lines = [
        f"🔎 <b>ResearchBrief</b> — {esc(brief.topic.title)}",
        f"Episode {short_id(ep.id)} · {_status_line(ep)}",
        f"<b>Tujuan:</b> {esc(clip(brief.objective, 300))}",
        f"<b>Sensitivitas:</b> {brief.sensitivity.value} — "
        f"{esc(clip(brief.sensitivity_reason, 160))}",
        f"<b>Mutu riset:</b> {'✅ LULUS' if report.passed else '❌ TIDAK LULUS'} "
        f"({report.verified_facts} fakta terverifikasi, minimal {report.min_verified_facts})",
        f"<b>Klaim:</b> {counts}",
        f"<b>Sumber:</b> {len(brief.sources)} ({tiers or '-'})"
        + (f" · {quarantined} dikarantina" if quarantined else ""),
        f"<b>Catatan fact-check:</b> {len(report.issues)} ({flagged} peringatan)",
    ]
    section_buttons = [
        button(f"{label.split(' ', 1)[0]} {len(_claims_of(view, cats))}", "r", ep.id, key, 0)
        for key, (label, cats) in RESEARCH_SECTIONS.items()
    ]
    return Screen(
        "\n".join(lines),
        rows(
            *grid(section_buttons, 4),
            [
                button(f"📚 Sumber ({len(brief.sources)})", "r", ep.id, "src", 0),
                button(f"⚠️ Catatan ({len(report.issues)})", "r", ep.id, "warn", 0),
            ],
            [button("🔗 Sumber per klaim", "r", ep.id, "clm", 0)],
            [button("📝 Naskah", "s", ep.id, "o"), button("📁 Episode", "e", ep.id)],
            menu_row(),
        ),
    )


def _source_label(view: ResearchView, source_ids: list[str]) -> str:
    tiers = {s.id: s.tier for s in view.brief.sources}
    return ", ".join(f"{sid} (t{tiers.get(sid, '?')})" for sid in source_ids) or "-"


def _research_claims(view: ResearchView, section: str, page_no: int) -> Screen:
    ep = view.episode
    label, cats = RESEARCH_SECTIONS[section]
    claims = _claims_of(view, cats)
    page = Page.of(claims, page_no, PER_PAGE)
    lines = [f"{label} ({page.total}) — {esc(clip(view.brief.topic.title, 40))}"]
    if not claims:
        lines.append("Tidak ada klaim di kategori ini.")
    for offset, claim in enumerate(page.items, start=page.page * PER_PAGE + 1):
        line = f"\n<b>{offset}.</b> {esc(clip(claim.statement, 280))}"
        line += f"\n   📎 {_source_label(view, claim.supporting_source_ids)}"
        if claim.contradicting_source_ids:
            line += f" · dibantah {_source_label(view, claim.contradicting_source_ids)}"
        line += f"\n   <code>{esc(claim.id)}</code>"
        if claim.category is ClaimCategory.UNVERIFIED or claim.category is ClaimCategory.DISPUTED:
            line += f"\n   <i>{esc(clip(claim.rationale, 160))}</i>"
        lines.append(line)
    all_claims = view.brief.all_claims()
    detail = [
        button(f"🔗 {all_claims.index(c) + 1}", "c", ep.id, all_claims.index(c)) for c in page.items
    ]
    return Screen(
        "\n".join(lines),
        rows(
            detail,
            pager("r", [ep.id, section], page.page, page.pages),
            [button("⬅️ Ringkasan riset", "r", ep.id, "sum", 0)],
            menu_row(),
        ),
    )


def _research_sources(view: ResearchView, page_no: int) -> Screen:
    ep = view.episode
    page = Page.of(view.brief.sources, page_no, SOURCES_PER_PAGE)
    lines = [f"📚 <b>Sumber</b> ({page.total})"]
    for s in page.items:
        flag = " · ⛔ dikarantina" if s.quarantined else ""
        lines.append(
            f"\n<b>{esc(s.id)}</b> · tier {s.tier} · skor {s.quality_score}{flag}\n"
            f"{esc(clip(s.title, 90))}\n{esc(clip(s.publisher, 60))}\n"
            f"{esc(s.url)}\n<i>diakses {esc(s.retrieved_at[:10])}"
            f"{' · ' + esc(s.published_date) if s.published_date else ''}</i>"
        )
    return Screen(
        "\n".join(lines),
        rows(
            pager("r", [ep.id, "src"], page.page, page.pages),
            [button("⬅️ Ringkasan riset", "r", ep.id, "sum", 0)],
            menu_row(),
        ),
    )


def _research_warnings(view: ResearchView, page_no: int) -> Screen:
    ep = view.episode
    page = Page.of(view.report.issues, page_no, 6)
    icon = {"blocking": "⛔", "warning": "⚠️", "info": "ℹ️"}
    lines = [f"⚠️ <b>Catatan fact-check</b> ({page.total})"]
    if not page.items:
        lines.append("Tidak ada catatan.")
    for issue in page.items:
        lines.append(
            f"{icon.get(issue.severity.value, '•')} <b>{esc(issue.code)}</b>: "
            f"{esc(clip(issue.message, 240))}"
        )
    return Screen(
        "\n".join(lines),
        rows(
            pager("r", [ep.id, "warn"], page.page, page.pages),
            [button("⬅️ Ringkasan riset", "r", ep.id, "sum", 0)],
            menu_row(),
        ),
    )


def claim_picker(view: ResearchView, page_no: int = 0) -> Screen:
    ep = view.episode
    claims = view.brief.all_claims()
    page = Page.of(list(enumerate(claims)), page_no, CLAIMS_PER_PAGE)
    lines = [texts.ASK_CLAIM]
    buttons = []
    for index, claim in page.items:
        lines.append(f"<b>{index + 1}.</b> {esc(clip(claim.statement, 90))}")
        buttons.append(button(f"{index + 1}. {clip(claim.statement, 28)}", "c", ep.id, index))
    return Screen(
        "\n".join(lines),
        rows(
            *grid(buttons, 1),
            pager("r", [ep.id, "clm"], page.page, page.pages),
            [button("⬅️ Ringkasan riset", "r", ep.id, "sum", 0)],
        ),
    )


def claim_sources(cs: ClaimSources, index: int) -> Screen:
    claim = cs.claim
    category = CATEGORY_LABEL[claim.category] if claim.category else "-"
    lines = [
        f"🔗 <b>Sumber klaim</b> <code>{esc(claim.id)}</code>",
        f"{esc(clip(claim.statement, 400))}",
        f"<b>Kategori:</b> {category} · {claim.independent_groups} kelompok sumber independen",
        f"<i>{esc(clip(claim.rationale, 240))}</i>",
    ]
    supporting = set(claim.supporting_source_ids)
    for s in cs.sources:
        role = "mendukung" if s.id in supporting else "membantah"
        lines.append(
            f"\n📚 <b>{esc(s.id)}</b> ({role}) · tier {s.tier} · skor {s.quality_score}\n"
            f"{esc(clip(s.title, 90))} — {esc(clip(s.publisher, 50))}\n{esc(s.url)}"
        )
    for e in cs.evidence[:4]:
        lines.append(f"\n❝{esc(clip(e.quote, 220))}❞ — {esc(e.source_id)}")
    if not cs.sources:
        lines.append("\nBelum ada sumber yang lolos verifikasi untuk klaim ini.")
    return Screen(
        "\n".join(lines),
        rows(
            [button("🔗 Klaim lain", "r", cs.episode.id, "clm", index // CLAIMS_PER_PAGE)],
            [button("⬅️ Ringkasan riset", "r", cs.episode.id, "sum", 0)],
            menu_row(),
        ),
    )


# --- naskah ----------------------------------------------------------------------


def _editorial_status(view: ScriptView) -> str:
    report = view.report
    if report is None:
        return "belum diperiksa"
    if report.passed:
        return "✅ LULUS"
    if report.overridden:
        return "⚠️ OVERRIDE OWNER"
    return "❌ TIDAK LULUS"


def script_screen(view: ScriptView, segment: str = "o") -> Screen:
    ep, script = view.episode, view.script
    if segment == "w":
        return _script_warnings(view)
    if segment.isdigit() and int(segment) < len(script.segments):
        return _script_segment(view, int(segment))
    warnings = len(view.report.issues) if view.report else 0
    lines = [
        f"📝 <b>{esc(script.title)}</b>",
        f"{esc(script.format_label)} · revisi {script.revision}",
        f"⏱ Estimasi <b>{script.estimated_duration_s:.1f} dtk</b> "
        f"(target {script.target_duration_s}) "
        f"· {script.word_count} kata · {script.words_per_minute} kata/menit",
        f"Editorial gate: {_editorial_status(view)} · {warnings} catatan",
        "",
    ]
    for seg in script.segments:
        lines.append(
            f"<b>{texts.SEGMENT_LABEL[seg.role]}</b> [{seg.start_s:.1f}–{seg.end_s:.1f} dtk] · "
            f"{esc(clip(seg.text, 90))}"
        )
    if script.notes:
        lines.append(f"\n<i>Catatan revisi: {esc(clip(script.notes, 200))}</i>")
    segment_buttons = [
        button(texts.SEGMENT_LABEL[seg.role], "s", ep.id, i)
        for i, seg in enumerate(script.segments)
    ]
    actions: list[Button] = [button(f"⚠️ Editorial ({warnings})", "s", ep.id, "w")]
    if ep.status is EpisodeStatus.AWAITING_EDITORIAL or (
        ep.status is EpisodeStatus.FAILED and ep.failed_from is EpisodeStatus.SCRIPTING
    ):
        actions.append(button("✏️ Minta revisi", "q", "revise", ep.id))
    return Screen(
        "\n".join(lines),
        rows(
            *grid(segment_buttons, 3),
            actions,
            [button("🔎 Riset", "r", ep.id, "sum", 0), button("📁 Episode", "e", ep.id)],
            menu_row(),
        ),
    )


def _script_segment(view: ScriptView, index: int) -> Screen:
    ep, script = view.episode, view.script
    seg = script.segments[index]
    lines = [
        f"📝 <b>{texts.SEGMENT_LABEL[seg.role]}</b> ({index + 1}/{len(script.segments)}) · "
        f"{seg.start_s:.1f}–{seg.end_s:.1f} dtk · {seg.word_count} kata",
        f"🎥 <i>{esc(clip(seg.visual_direction, 200))}</i>",
    ]
    for line in seg.lines:
        refs = ", ".join(line.claim_refs) or "—"
        lines.append(f"\n• {esc(line.text)}\n  ↳ <code>{esc(refs)}</code>")
    nav: list[Button] = []
    if index > 0:
        nav.append(
            button(
                f"◀️ {texts.SEGMENT_LABEL[script.segments[index - 1].role]}", "s", ep.id, index - 1
            )
        )
    if index < len(script.segments) - 1:
        nav.append(
            button(
                f"{texts.SEGMENT_LABEL[script.segments[index + 1].role]} ▶️", "s", ep.id, index + 1
            )
        )
    return Screen(
        "\n".join(lines),
        rows(nav, [button("⬅️ Ringkasan naskah", "s", ep.id, "o")], menu_row()),
    )


def _script_warnings(view: ScriptView) -> Screen:
    ep = view.episode
    report = view.report
    lines = [f"⚠️ <b>Laporan editorial</b> — {_editorial_status(view)}"]
    if report is None:
        lines.append("Belum ada laporan editorial.")
    else:
        icon = {"blocking": "⛔", "warning": "⚠️", "info": "ℹ️"}
        for issue in report.issues[:15]:
            where = (
                f" (segmen {issue.segment_index + 1})" if issue.segment_index is not None else ""
            )
            lines.append(
                f"{icon.get(issue.severity.value, '•')} <b>{esc(issue.code)}</b>{where}: "
                f"{esc(clip(issue.message, 200))}"
            )
        if len(report.issues) > 15:
            lines.append(f"… dan {len(report.issues) - 15} catatan lain")
        for instruction in report.revision_instructions[:5]:
            lines.append(f"→ {esc(clip(instruction, 200))}")
        if report.overridden and report.override_reason:
            lines.append(
                f"\n<i>Alasan override owner: {esc(clip(report.override_reason, 200))}</i>"
            )
        if not report.issues:
            lines.append("Tidak ada catatan.")
    return Screen(
        "\n".join(lines), rows([button("⬅️ Ringkasan naskah", "s", ep.id, "o")], menu_row())
    )


# --- approval --------------------------------------------------------------------


def _detail_button(approval: Approval) -> Button:
    episode_id = approval.episode_id
    return {
        Gate.TOPIC: button("🔍 Detail", "t", episode_id),
        Gate.EDITORIAL: button("🔍 Detail", "s", episode_id, "o"),
        Gate.COST: button("🔍 Detail", "$", episode_id),
        Gate.FINAL: button("🔍 Detail", "e", episode_id),
    }[approval.gate]


def approval_card(card: ApprovalCard, extra: str = "") -> Screen:
    approval, ep = card.approval, card.episode
    lines = [
        f"🗳 <b>{texts.GATE_LABEL[approval.gate]}</b>",
        f"Episode <b>{esc(episode_name(ep))}</b> {short_id(ep.id)} · "
        f"versi {approval.episode_version}",
    ]
    if extra:
        lines.insert(0, extra)
    if approval.gate is Gate.EDITORIAL and card.editorial:
        lines.append(esc(card.editorial))
    if card.simulated:
        lines.append(texts.SIMULATION_NOTE)
    if approval.spend_cap_idr is not None:
        lines.append(
            f"Batas belanja yang disetujui: {format_idr(approval.spend_cap_idr)} (simulasi)"
        )
    if card.topics:
        lines.append("")
        lines.extend(_topic_block(n, t) for n, t in enumerate(card.topics, start=1))
    lines.append(f"\n<i>Tombol berlaku sampai {card.expires_at:%d %b %H:%M} UTC · sekali pakai</i>")
    decision: list[list[Button]] = []
    if approval.gate is Gate.TOPIC:
        choices = [
            action(f"✅ {n}", card.codes[f"choose:{n}"]) for n in range(1, len(card.topics) + 1)
        ]
        decision.append(choices)
    else:
        decision.append([action("✅ Approve", card.codes["approve"])])
    decision.append(
        [
            action("❌ Reject", card.codes["reject"]),
            action("✏️ Request Revision", card.codes["revise"]),
        ]
    )
    return Screen("\n".join(lines), rows(*decision, [_detail_button(approval)]))


def revise_card(card: ReviseCard) -> Screen:
    lines = [
        f"✏️ <b>Minta revisi</b> — {texts.GATE_LABEL[card.approval.gate]}",
        f"Episode {esc(episode_name(card.episode))} {short_id(card.episode.id)}",
        "Pilih tahap yang perlu diulang. Approval di gate ini (dan setelahnya) akan dibatalkan.",
    ]
    targets = [
        [action(texts.REVISION_TARGET_LABEL.get(EpisodeStatus(t), t), card.codes[f"to:{t}"])]
        for t in card.targets
    ]
    return Screen("\n".join(lines), rows(*targets, [action("⬅️ Kembali", card.codes["back"])]))


def confirm_card(card: ConfirmCard, title: str) -> Screen:
    text = f"❓ <b>{esc(title)}</b>\n{esc(card.summary)}"
    if card.episode is not None:
        text += f"\nEpisode: {esc(episode_name(card.episode))} {short_id(card.episode.id)}"
    return Screen(
        text,
        rows([action("✅ Ya, lanjutkan", card.codes["yes"]), action("Batal", card.codes["no"])]),
    )


def pending_list(items: list[ApprovalSummary], page_no: int = 0) -> Screen:
    if not items:
        return Screen(texts.NO_PENDING, rows(menu_row()))
    page = Page.of(items, page_no, 6)
    lines = [f"✅ <b>Menunggu keputusan Anda</b> ({page.total})"]
    buttons = []
    for item in page.items:
        lines.append(
            f"• {texts.GATE_LABEL[item.approval.gate]} — <b>{esc(episode_name(item.episode))}</b> "
            f"{short_id(item.episode.id)}\n  "
            + (
                "⌛ sudah kedaluwarsa — buka untuk terbitkan ulang"
                if item.expired
                else f"kedaluwarsa {item.approval.expires_at:%d %b %H:%M} UTC"
            )
        )
        buttons.append(
            [
                button(
                    f"🗳 {item.approval.gate.value} · {clip(episode_name(item.episode), 26)}",
                    "ap",
                    item.approval.id,
                )
            ]
        )
    return Screen(
        "\n".join(lines), rows(*buttons, pager("pa", [], page.page, page.pages), menu_row())
    )


# --- budget, biaya, status, pengaturan ---------------------------------------------


def budget_screen(dash: BudgetDashboard) -> Screen:
    state_text = "aktif" if dash.active else "BELUM DIAKTIFKAN"
    lines = [
        f"💰 <b>Budget {esc(dash.period)}</b> ({state_text})",
        f"Anggaran bulanan: <b>{format_idr(dash.monthly_budget_idr)}</b>",
        f"Kurs asumsi USD/IDR: {fx_text(dash.fx_usd_idr)} (per {esc(dash.fx_as_of)}, dari config)",
        f"VPS (estimasi): USD {esc(dash.vps_usd)} = {format_idr(dash.vps_idr)}",
        "",
    ]
    for line in dash.lines:
        label = texts.BUDGET_CATEGORY_LABEL.get(line.name, line.name)
        if line.spendable:
            lines.append(
                f"<b>{label}</b>: {format_idr(line.allocation_idr)}\n"
                f"  terpakai simulasi {format_idr(line.used_simulated_idr)} · "
                f"real {format_idr(line.used_real_idr)}\n"
                f"  sisa {format_idr(line.remaining_idr)}"
            )
        else:
            lines.append(
                f"<b>{label}</b>: {format_idr(line.allocation_idr)} (tidak bisa dibelanjakan)"
            )
    lines.append(
        f"\nTotal terpakai: simulasi {format_idr(dash.simulated.used_idr)} · "
        f"real {format_idr(dash.real.used_idr)}"
    )
    for source, used in sorted(dash.by_source_simulated.items()):
        lines.append(f"  sumber {esc(source)}: {format_idr(used)} (simulasi)")
    paid = "AKTIF" if dash.paid_providers_enabled else "NONAKTIF"
    lines.append(f"\n⚠️ Fase 3: semua biaya masih <b>SIMULASI</b> (mock). API berbayar: {paid}.")
    extra: list[Button] = [] if dash.active else [button("▶️ Aktifkan periode", "q", "budget", "-")]
    return Screen("\n".join(lines), rows(extra, menu_row()))


def cost_screen(cost: EpisodeCost) -> Screen:
    ep = cost.episode
    lines = [
        f"💸 <b>Biaya episode</b> {esc(episode_name(ep))} {short_id(ep.id)}",
        f"Terpakai: {format_idr(cost.spent_simulated_idr)} (simulasi) · "
        f"{format_idr(cost.spent_real_idr)} (real)",
        f"Pra-produksi (riset & naskah): {format_idr(cost.preproduction_used_idr)} dari batas "
        f"{format_idr(cost.preproduction_cap_idr or 0)}",
        f"Panggilan LLM tercatat: {cost.llm_calls}",
    ]
    if cost.estimate is not None:
        est = cost.estimate
        lines.append(
            f"\n<b>Estimasi produksi (G2, simulasi)</b> · harga {esc(est.pricing_version)}"
        )
        for line in est.lines:
            lines.append(
                f"  • {esc(line.label)}: {line.quantity} × {esc(line.price_key)} = "
                f"{format_idr(line.idr)}"
            )
        for category, amount in sorted(est.by_category().items()):
            label = texts.BUDGET_CATEGORY_LABEL.get(category.value, category.value)
            remaining = cost.remaining_by_category.get(category.value)
            left = f" · sisa anggaran {format_idr(remaining)}" if remaining is not None else ""
            lines.append(f"  {esc(label)}: {format_idr(amount)}{left}")
        lines.append(
            f"  Total {format_idr(est.total_idr)} · batas maksimum (+{est.margin_pct}%) "
            f"{format_idr(est.cap_idr)}"
        )
        lines.append(f"  Kurs USD/IDR {fx_text(est.fx.as_text)} (per {est.fx.as_of.isoformat()})")
    else:
        lines.append("Estimasi produksi: belum dihitung (dibuat setelah G1 disetujui).")
    lines.append("\n⚠️ Semua angka Fase 3 adalah biaya simulasi dari mock provider.")
    return Screen("\n".join(lines), rows([button("📁 Episode", "e", ep.id)], menu_row()))


def production_screen(items: list[ProductionItem]) -> Screen:
    if not items:
        return Screen("⚙️ Tidak ada episode yang sedang diproses atau gagal.", rows(menu_row()))
    lines = ["⚙️ <b>Status produksi</b>"]
    buttons = []
    for item in items[:10]:
        ep = item.episode
        lines.append(f"\n<b>{esc(episode_name(ep))}</b> {short_id(ep.id)}\n  {_status_line(ep)}")
        for job in item.jobs:
            retry = f" · percobaan {job.attempts}/{job.max_attempts}" if job.attempts else ""
            lines.append(f"  job {job.status.value}{retry}")
            if job.last_error:
                lines.append(f"  ↳ terakhir gagal: {esc(clip(job.last_error, 140))}")
        if ep.status is EpisodeStatus.FAILED:
            lines.append(f"  ❗ {esc(clip(ep.failure_reason or '-', 200))}")
            buttons.append([button(f"🔁 Ulangi {short_id(ep.id)}", "q", "retry", ep.id)])
        else:
            buttons.append([button(f"📁 {clip(episode_name(ep), 30)}", "e", ep.id)])
    return Screen("\n".join(lines), rows(*buttons, menu_row()))


def settings_screen(view: StudioSettingsView) -> Screen:
    formats = "\n".join(
        f"  • {esc(spec.label)}: {spec.min_s}–{spec.max_s} dtk (default {spec.default_s})"
        for spec in view.formats.values()
    )
    lines = [
        "🛠 <b>Pengaturan</b> (baca saja; ubah lewat config/.env)",
        f"Akun owner: <code>{esc(view.owner_label)}</code>",
        f"Masa berlaku approval: {view.approval_ttl_hours} jam",
        f"Masa berlaku tombol aksi: {view.action_ttl_minutes} menit",
        f"Kecepatan narasi: {view.words_per_minute} kata/menit",
        f"Format:\n{formats}",
        f"Penerima notifikasi: {view.notification_recipients} owner Telegram",
        f"Provider: mock (API berbayar {'AKTIF' if view.paid_providers_enabled else 'NONAKTIF'})",
    ]
    return Screen("\n".join(lines), rows(menu_row()))

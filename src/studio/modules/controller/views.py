"""Read model untuk antarmuka chat. Hanya data; tidak ada logika bisnis di sini."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from studio.infra.jobs import Job
from studio.modules.approvals import Approval
from studio.modules.budget import BudgetStatus, CostEstimate
from studio.modules.episodes import Episode
from studio.modules.research import (
    ClaimRecord,
    EvidenceRecord,
    ResearchBrief,
    ResearchQualityReport,
    SourceRecord,
    TopicCandidate,
)
from studio.modules.scripting import DocumentaryScript, EditorialReport, FormatSpec


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    page: int  # mulai dari 0
    pages: int
    total: int

    @classmethod
    def of(cls, items: list[T], page: int, per_page: int) -> Page[T]:
        pages = max(1, -(-len(items) // per_page))
        page = min(max(page, 0), pages - 1)
        return cls(items[page * per_page : (page + 1) * per_page], page, pages, len(items))


class EpisodeFilter(StrEnum):
    ACTIVE = "active"  # belum selesai/ditutup
    AWAITING = "awaiting"  # menunggu keputusan owner
    WORKING = "working"  # sedang diproses worker
    ALL = "all"


@dataclass(frozen=True)
class EpisodeSummary:
    episode: Episode
    pending: Approval | None


@dataclass(frozen=True)
class EpisodeDetail:
    episode: Episode
    pending: list[Approval]
    artifact_kinds: list[str]
    spent_simulated_idr: int
    spent_real_idr: int
    jobs: list[Job]


@dataclass(frozen=True)
class ResearchView:
    episode: Episode
    brief: ResearchBrief
    report: ResearchQualityReport


@dataclass(frozen=True)
class ScriptView:
    episode: Episode
    script: DocumentaryScript
    report: EditorialReport | None


@dataclass(frozen=True)
class ClaimSources:
    episode: Episode
    claim: ClaimRecord
    sources: list[SourceRecord]
    evidence: list[EvidenceRecord]


@dataclass(frozen=True)
class CategoryLine:
    name: str
    allocation_idr: int
    used_simulated_idr: int
    used_real_idr: int
    remaining_idr: int  # sisa untuk mode simulasi (yang dipakai Fase 3)
    spendable: bool


@dataclass(frozen=True)
class BudgetDashboard:
    period: str
    active: bool
    monthly_budget_idr: int
    vps_usd: str
    vps_idr: int
    fx_usd_idr: str
    fx_as_of: str
    lines: list[CategoryLine]
    simulated: BudgetStatus
    real: BudgetStatus
    paid_providers_enabled: bool
    by_source_simulated: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class EpisodeCost:
    episode: Episode
    spent_simulated_idr: int
    spent_real_idr: int
    preproduction_cap_idr: int | None
    preproduction_used_idr: int
    production_estimate_idr: int | None
    production_cap_idr: int | None
    llm_calls: int
    estimate: CostEstimate | None = None  # rincian G2 (simulasi di Fase 3)
    remaining_by_category: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovalSummary:
    approval: Approval
    episode: Episode
    expired: bool = False


@dataclass(frozen=True)
class ApprovalCard:
    approval: Approval
    episode: Episode
    codes: dict[str, str]
    expires_at: datetime
    topics: list[TopicCandidate]
    simulated: bool  # G2/G3 masih placeholder simulasi di Fase 3
    editorial: str = ""  # ringkasan naskah + editorial gate untuk kartu G1


@dataclass(frozen=True)
class ReviseCard:
    approval: Approval
    episode: Episode
    targets: list[str]
    codes: dict[str, str]


@dataclass(frozen=True)
class ConfirmCard:
    """Konfirmasi aksi sensitif (kirim revisi, buat episode, batalkan, aktifkan periode)."""

    action: str
    summary: str
    codes: dict[str, str]  # "yes" / "no"
    episode: Episode | None = None


class Outcome(StrEnum):
    DONE = "done"
    NEEDS_NOTES = "needs_notes"  # target revisi dipilih; tunggu catatan
    REVISE_MENU = "revise_menu"
    STALE = "stale"  # konten berubah; ada kartu pengganti
    EXPIRED = "expired"  # approval kedaluwarsa; tawarkan terbitkan ulang
    REFUSED = "refused"  # kode tidak berlaku / sudah dipakai / milik orang lain
    FAILED = "failed"  # ditolak aturan bisnis (pesan aman untuk owner)
    DISMISSED = "dismissed"


@dataclass(frozen=True)
class ActionReply:
    outcome: Outcome
    message: str
    episode: Episode | None = None
    approval: Approval | None = None
    revise: ReviseCard | None = None
    pending_action_id: str | None = None  # langkah lanjutan (misal menunggu catatan revisi)
    revise_to: str | None = None


@dataclass(frozen=True)
class ProductionItem:
    episode: Episode
    jobs: list[Job]


@dataclass(frozen=True)
class StudioSettingsView:
    owner_label: str
    approval_ttl_hours: int
    action_ttl_minutes: int
    words_per_minute: int
    formats: dict[str, FormatSpec]
    paid_providers_enabled: bool
    notification_recipients: int

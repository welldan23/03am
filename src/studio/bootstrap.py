"""Composition root: satu-satunya tempat semua komponen dirakit.

Adapter provider (termasuk mock) hanya dibuat di sini. Modul domain menerima `LLMClient`
yang selalu lewat `MeteredCaller` → BudgetGuard; provider mentah tidak diekspos ke luar.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import yaml
from pydantic import ValidationError

from studio.infra.db import Database, migrate
from studio.infra.jobs import JobQueue, Worker
from studio.modules.approvals import ApprovalService
from studio.modules.artifacts import ArtifactStore
from studio.modules.audit import AuditLog
from studio.modules.budget import (
    BudgetGuard,
    BudgetPlan,
    BudgetService,
    PricingTable,
    load_plan,
    load_pricing,
)
from studio.modules.calls import LLMClient, MeteredCaller, PromptLibrary, load_llm_config
from studio.modules.controller import (
    ActionCodes,
    ControllerConfig,
    ConversationStore,
    StudioController,
    UpdateLog,
)
from studio.modules.episodes import EpisodeService
from studio.modules.notifications import Outbox
from studio.modules.research import ResearchConfig, ResearchEngine
from studio.modules.scripting import ScriptEngine, ScriptingConfig
from studio.modules.workflow import WorkflowService
from studio.modules.workflow.stages import ContentStages
from studio.providers.llm.mock import MockLLMProvider
from studio.providers.llm.ports import LLMProvider
from studio.providers.sources.mock import FixtureSourceLibrary
from studio.providers.sources.ports import SourceProvider
from studio.providers.tickets import TicketAuthority
from studio.shared.actors import OwnerPolicy
from studio.shared.clock import Clock, SystemClock
from studio.shared.config import Settings
from studio.shared.errors import ConfigError
from studio.shared.ids import new_id

LLMProviderFactory = Callable[[TicketAuthority], LLMProvider]


@dataclass
class App:
    settings: Settings
    clock: Clock
    db: Database
    owners: OwnerPolicy
    plan: BudgetPlan
    pricing: PricingTable
    audit: AuditLog
    episodes: EpisodeService
    artifacts: ArtifactStore
    approvals: ApprovalService
    budget: BudgetService
    guard: BudgetGuard
    queue: JobQueue
    calls: MeteredCaller
    research: ResearchEngine
    scripts: ScriptEngine
    workflow: WorkflowService
    controller: StudioController
    actions: ActionCodes
    conversations: ConversationStore
    updates: UpdateLog
    outbox: Outbox

    def worker(self, worker_id: str | None = None) -> Worker:
        return Worker(
            self.db,
            self.queue,
            self.workflow.handlers(),
            worker_id=worker_id or f"worker-{new_id(self.clock)}",
            lease_seconds=self.settings.worker_lease_seconds,
            on_dead=self.workflow.on_job_dead,
        )

    def close(self) -> None:
        self.db.close()


def check_paid_providers(settings: Settings, plan: BudgetPlan) -> None:
    """Tolak start kalau provider berbayar diminta aktif. Fase 2 belum punya adapter asli."""
    if not settings.paid_providers_enabled:
        return
    problems = [
        "belum ada adapter provider berbayar (Fase 2 hanya mock)",
        *plan.paid_activation_issues(),
    ]
    raise ConfigError("PAID_PROVIDERS_ENABLED=true ditolak: " + "; ".join(problems))


def load_editorial_config(path: Path) -> tuple[ResearchConfig, ScriptingConfig]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        research = ResearchConfig.model_validate(raw["research"])
        scripting = ScriptingConfig.model_validate(
            {k: raw[k] for k in ("narration", "formats", "editorial")}
        )
    except (FileNotFoundError, KeyError, TypeError, ValidationError) as exc:
        raise ConfigError(f"konfigurasi editorial tidak valid ({path}): {exc}") from exc
    return research, scripting


def build_app(
    settings: Settings,
    *,
    clock: Clock | None = None,
    llm_provider_factory: LLMProviderFactory | None = None,
    source_provider: SourceProvider | None = None,
) -> App:
    clock = clock or SystemClock()
    plan = load_plan(settings.budget_config_path)
    pricing = load_pricing(settings.pricing_config_path)
    llm_config = load_llm_config(settings.llm_config_path)
    research_config, scripting_config = load_editorial_config(settings.editorial_config_path)
    check_paid_providers(settings, plan)

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_path)
    migrate(db, clock=clock)

    owners = OwnerPolicy(settings.owner_id_set)
    audit = AuditLog(db, clock)
    episodes = EpisodeService(db, clock, audit)
    artifacts = ArtifactStore(db, clock)
    approvals = ApprovalService(
        db, clock, audit, owners, ttl=timedelta(hours=settings.approval_ttl_hours)
    )
    budget = BudgetService(db, clock, audit, owners, plan)
    guard = BudgetGuard(
        db, clock, audit, plan, paid_providers_enabled=settings.paid_providers_enabled
    )
    queue = JobQueue(db, clock, default_max_attempts=settings.job_max_attempts)

    tickets = TicketAuthority()
    provider = (
        llm_provider_factory
        or (lambda t: MockLLMProvider(t, chars_per_token=llm_config.chars_per_token))
    )(tickets)
    caller = MeteredCaller(
        db,
        clock,
        audit,
        guard,
        budget,
        pricing,
        provider,
        tickets,
        chars_per_token=llm_config.chars_per_token,
    )
    llm = LLMClient(caller, llm_config, PromptLibrary())
    research = ResearchEngine(
        llm, source_provider or FixtureSourceLibrary(), research_config, clock
    )
    scripts = ScriptEngine(llm, scripting_config)
    stages = ContentStages(
        artifacts=artifacts, approvals=approvals, research=research, scripts=scripts
    )
    workflow = WorkflowService(
        db=db,
        audit=audit,
        owners=owners,
        episodes=episodes,
        artifacts=artifacts,
        approvals=approvals,
        budget=budget,
        guard=guard,
        queue=queue,
        pricing=pricing,
        plan=plan,
        stages=stages,
        scripting=scripting_config,
    )
    actions = ActionCodes(db, clock, audit)
    controller = StudioController(
        db=db,
        clock=clock,
        audit=audit,
        owners=owners,
        episodes=episodes,
        artifacts=artifacts,
        approvals=approvals,
        budget=budget,
        plan=plan,
        queue=queue,
        calls=caller,
        workflow=workflow,
        scripting=scripting_config,
        actions=actions,
        config=ControllerConfig(
            action_ttl=timedelta(minutes=settings.action_ttl_minutes),
            approval_ttl_hours=settings.approval_ttl_hours,
            paid_providers_enabled=settings.paid_providers_enabled,
            notification_recipients=settings.telegram_owner_ids,
        ),
    )
    return App(
        settings=settings,
        clock=clock,
        db=db,
        owners=owners,
        plan=plan,
        pricing=pricing,
        audit=audit,
        episodes=episodes,
        artifacts=artifacts,
        approvals=approvals,
        budget=budget,
        guard=guard,
        queue=queue,
        calls=caller,
        research=research,
        scripts=scripts,
        workflow=workflow,
        controller=controller,
        actions=actions,
        conversations=ConversationStore(
            db, clock, step_ttl=timedelta(minutes=settings.conversation_step_ttl_minutes)
        ),
        updates=UpdateLog(db, clock),
        outbox=Outbox(db, clock),
    )

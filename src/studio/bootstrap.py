"""Composition root: satu-satunya tempat semua komponen dirakit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

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
from studio.modules.episodes import EpisodeService
from studio.modules.workflow import WorkflowService
from studio.shared.actors import OwnerPolicy
from studio.shared.clock import Clock, SystemClock
from studio.shared.config import Settings
from studio.shared.errors import ConfigError
from studio.shared.ids import new_id


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
    workflow: WorkflowService

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
    """Tolak start kalau provider berbayar diminta aktif. Fase 1 belum punya adapter asli."""
    if not settings.paid_providers_enabled:
        return
    problems = ["Fase 1 belum punya adapter provider berbayar", *plan.paid_activation_issues()]
    raise ConfigError("PAID_PROVIDERS_ENABLED=true ditolak: " + "; ".join(problems))


def build_app(settings: Settings, *, clock: Clock | None = None) -> App:
    clock = clock or SystemClock()
    plan = load_plan(settings.budget_config_path)
    pricing = load_pricing(settings.pricing_config_path)
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
        workflow=workflow,
    )

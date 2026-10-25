"""CLI owner untuk menguji alur Fase 1 tanpa Telegram.

Contoh:
    studio budget activate
    studio episode new --category sejarah --duration 60
    studio episode start <ID>
    studio worker run
    studio approval list
    studio approval approve <APPROVAL_ID> --choice 1
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections.abc import Callable, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, TextIO

import yaml

from studio.bootstrap import App, build_app
from studio.infra.jobs import JobStatus
from studio.modules.approvals import Decision
from studio.modules.artifacts import ArtifactKind
from studio.modules.budget import Mode, propose_reallocation
from studio.modules.episodes import Category, DocumentaryFormat, EpisodeStatus
from studio.modules.research import (
    CATEGORY_LABEL,
    ClaimCategory,
    ResearchBrief,
    ResearchQualityReport,
)
from studio.modules.scripting import DocumentaryScript, EditorialReport
from studio.shared.actors import Actor
from studio.shared.config import Settings
from studio.shared.errors import StudioError
from studio.shared.gates import Gate
from studio.shared.logging import configure_logging
from studio.shared.money import format_idr, format_usd

Command = Callable[[App, argparse.Namespace, TextIO], None]


def parse_actor(value: str) -> Actor:
    """Actor untuk perintah CLI.

    - `director:<nama>` / `system:<nama>` untuk simulasi peran non-manusia;
    - owner HANYA boleh beridentitas `cli:<nama>`. CLI tidak bisa menyamar sebagai owner
      dari kanal lain (misalnya `telegram:<id>`), dan tetap harus ada di STUDIO_OWNER_IDS.
    """
    if value.startswith("director:"):
        return Actor.director(value.removeprefix("director:"))
    if value.startswith("system:"):
        return Actor.system(value.removeprefix("system:"))
    if not value.startswith("cli:") or value == "cli:":
        raise StudioError(f"actor CLI tidak sah: {value!r}; owner lewat CLI harus 'cli:<nama>'")
    return Actor.owner(value)


def _actor(args: argparse.Namespace) -> Actor:
    return parse_actor(args.actor)


# --- episode ---------------------------------------------------------------


def cmd_episode_new(app: App, args: argparse.Namespace, out: TextIO) -> None:
    episode = app.workflow.create_episode(
        category=Category(args.category),
        target_duration_s=args.duration,
        idea=args.idea,
        actor=_actor(args),
        format=DocumentaryFormat(args.format) if args.format else None,
    )
    fmt = episode.format.value if episode.format else "format otomatis"
    print(
        f"Episode dibuat: {episode.id} ({episode.category.value}, {episode.target_duration_s}s, "
        f"{fmt})",
        file=out,
    )


def cmd_episode_list(app: App, args: argparse.Namespace, out: TextIO) -> None:
    status = EpisodeStatus(args.status) if args.status else None
    episodes = app.episodes.list_episodes(status)
    if not episodes:
        print("Belum ada episode.", file=out)
    for ep in episodes:
        print(
            f"{ep.id}  {ep.status.value:<20} {ep.category.value:<10} "
            f"{ep.target_duration_s:>3}s  {ep.title or '-'}",
            file=out,
        )


def cmd_episode_show(app: App, args: argparse.Namespace, out: TextIO) -> None:
    ep = app.episodes.get(args.episode_id)
    print(f"Episode   : {ep.id}", file=out)
    print(f"Status    : {ep.status.value} (versi {ep.version})", file=out)
    print(f"Kategori  : {ep.category.value}, durasi {ep.target_duration_s}s", file=out)
    print(f"Judul     : {ep.title or '-'}", file=out)
    if ep.failure_reason:
        print(
            f"Gagal di  : {ep.failed_from.value if ep.failed_from else '-'} — {ep.failure_reason}",
            file=out,
        )
    for kind, artifact in app.artifacts.all_latest(ep.id).items():
        print(f"Artefak   : {kind.value} v{artifact.version}", file=out)
    for approval in app.approvals.pending(ep.id):
        print(f"Menunggu  : {approval.gate.value} → approval {approval.id}", file=out)
    spent = sum(e.actual_idr or 0 for e in app.budget.ledger(episode_id=ep.id))
    print(f"Biaya     : {format_idr(spent)} (simulasi)", file=out)


def cmd_episode_history(app: App, args: argparse.Namespace, out: TextIO) -> None:
    for entry in app.audit.entries(episode_id=args.episode_id):
        print(
            f"{entry.at:%Y-%m-%d %H:%M:%S}  {entry.actor:<24} {entry.action:<28} "
            f"{json.dumps(entry.data, ensure_ascii=False)}",
            file=out,
        )


def cmd_episode_start(app: App, args: argparse.Namespace, out: TextIO) -> None:
    ep = app.workflow.start(args.episode_id, _actor(args))
    print(f"Episode {ep.id} dimulai → {ep.status.value}. Jalankan `studio worker run`.", file=out)


def cmd_episode_cancel(app: App, args: argparse.Namespace, out: TextIO) -> None:
    ep = app.workflow.cancel(args.episode_id, _actor(args), args.reason)
    print(f"Episode {ep.id} → {ep.status.value}", file=out)


def cmd_episode_retry(app: App, args: argparse.Namespace, out: TextIO) -> None:
    ep = app.workflow.retry(args.episode_id, _actor(args))
    print(f"Episode {ep.id} diulang dari {ep.status.value}", file=out)


# --- approval --------------------------------------------------------------


def cmd_approval_list(app: App, args: argparse.Namespace, out: TextIO) -> None:
    pending = app.approvals.pending(args.episode)
    if not pending:
        print("Tidak ada approval yang menunggu.", file=out)
    for a in pending:
        cap = f" batas {format_idr(a.spend_cap_idr)}" if a.spend_cap_idr is not None else ""
        print(
            f"{a.id}  {a.gate.value}  episode {a.episode_id}{cap}  "
            f"kedaluwarsa {a.expires_at:%Y-%m-%d %H:%M} UTC",
            file=out,
        )


def cmd_approval_show(app: App, args: argparse.Namespace, out: TextIO) -> None:
    a = app.approvals.get(args.approval_id)
    print(f"Approval  : {a.id} ({a.gate.value}) — {a.status.value}", file=out)
    print(f"Episode   : {a.episode_id} versi {a.episode_version}", file=out)
    if a.spend_cap_idr is not None:
        print(f"Batas     : {format_idr(a.spend_cap_idr)}", file=out)
    print(f"Subjek    : {json.dumps(a.subject, ensure_ascii=False)}", file=out)
    if a.gate is Gate.COST:
        estimate = app.artifacts.latest(a.episode_id, ArtifactKind.COST_ESTIMATE)
        if estimate is not None:
            content = estimate.content
            for line in content["lines"]:
                print(
                    f"  - {line['label']:<12} {line['quantity']:>6} × "
                    f"{line['price_key']:<24} = {format_idr(line['idr'])}",
                    file=out,
                )
            print(
                f"  Total {format_idr(content['total_idr'])}, kurs {content['fx_usd_idr']} "
                f"({content['fx_as_of']}), batas {format_idr(content['cap_idr'])}",
                file=out,
            )


def _decide(app: App, args: argparse.Namespace, out: TextIO, decision: Decision) -> None:
    ep = app.workflow.decide(
        args.approval_id,
        decision,
        actor=_actor(args),
        notes=getattr(args, "notes", None),
        choice=getattr(args, "choice", None),
        revise_to=EpisodeStatus(args.to) if getattr(args, "to", None) else None,
    )
    print(f"Keputusan '{decision.value}' diterima. Episode {ep.id} → {ep.status.value}", file=out)


def cmd_approval_approve(app: App, args: argparse.Namespace, out: TextIO) -> None:
    _decide(app, args, out, Decision.APPROVE)


def cmd_approval_reject(app: App, args: argparse.Namespace, out: TextIO) -> None:
    _decide(app, args, out, Decision.REJECT)


def cmd_approval_revise(app: App, args: argparse.Namespace, out: TextIO) -> None:
    _decide(app, args, out, Decision.REVISE)


def cmd_approval_reissue(app: App, args: argparse.Namespace, out: TextIO) -> None:
    approval = app.workflow.reissue_approval(args.episode_id, _actor(args))
    print(f"Approval baru: {approval.id} ({approval.gate.value})", file=out)


# --- riset, naskah, panggilan LLM (Fase 2) ------------------------------------------


def cmd_episode_override(app: App, args: argparse.Namespace, out: TextIO) -> None:
    ep = app.workflow.override_editorial(args.episode_id, _actor(args), args.reason)
    print(
        f"Override editorial tercatat. Episode {ep.id} → {ep.status.value}. "
        "Jalankan `studio worker run`; keputusan G1 tetap di tangan owner.",
        file=out,
    )


def _require(app: App, episode_id: str, kind: ArtifactKind) -> dict[str, Any]:
    artifact = app.artifacts.latest(episode_id, kind)
    if artifact is None:
        raise StudioError(f"artefak {kind.value} belum ada untuk episode {episode_id}")
    return artifact.content


def cmd_research_show(app: App, args: argparse.Namespace, out: TextIO) -> None:
    content = _require(app, args.episode_id, ArtifactKind.FACTCHECK)
    if args.json:
        print(json.dumps(content["brief"], ensure_ascii=False, indent=2), file=out)
        return
    brief = ResearchBrief.model_validate(content["brief"])
    report = ResearchQualityReport.model_validate(content["quality_report"])
    print(f"Topik     : {brief.topic.title} [{brief.topic.topic_category.value}]", file=out)
    print(f"Tujuan    : {brief.objective}", file=out)
    print(f"Sensitif  : {brief.sensitivity.value} — {brief.sensitivity_reason}", file=out)
    print(
        f"Mutu riset: {'LULUS' if report.passed else 'TIDAK LULUS'} "
        f"({report.verified_facts} fakta terverifikasi, minimal {report.min_verified_facts})",
        file=out,
    )
    groups = [
        (ClaimCategory.VERIFIED_FACT, brief.verified_facts),
        (ClaimCategory.INTERPRETATION, brief.interpretations),
        (ClaimCategory.HYPOTHESIS, brief.hypotheses),
        (ClaimCategory.DISPUTED, brief.disputed),
        (ClaimCategory.UNVERIFIED, brief.unverified),
    ]
    for category, claims in groups:
        print(f"\n{CATEGORY_LABEL[category]} ({len(claims)})", file=out)
        for claim in claims:
            print(f"  {claim.id}: {claim.statement}", file=out)
            against = ", ".join(claim.contradicting_source_ids)
            print(
                f"      sumber {', '.join(claim.supporting_source_ids) or '-'}"
                f"{'; dibantah ' + against if against else ''} — {claim.rationale}",
                file=out,
            )
    print("\nSumber", file=out)
    for source in brief.sources:
        print(
            f"  {source.id} tier {source.tier} skor {source.quality_score} "
            f"[{source.independence_group}] {source.publisher} — {source.url} "
            f"(diakses {source.retrieved_at[:10]})",
            file=out,
        )
    if report.issues:
        print("\nCatatan mutu", file=out)
        for issue in report.issues:
            print(f"  [{issue.severity.value}] {issue.code}: {issue.message}", file=out)


def cmd_script_show(app: App, args: argparse.Namespace, out: TextIO) -> None:
    content = _require(app, args.episode_id, ArtifactKind.SCRIPT)
    script = DocumentaryScript.model_validate(
        {k: v for k, v in content.items() if k != "llm_calls"}
    )
    print(f"{script.title} — {script.format_label} (revisi {script.revision})", file=out)
    print(
        f"Estimasi {script.estimated_duration_s}s untuk target {script.target_duration_s}s · "
        f"{script.word_count} kata · {script.words_per_minute} kata/menit",
        file=out,
    )
    for segment in script.segments:
        print(
            f"\n[{segment.start_s:>5.1f}–{segment.end_s:>5.1f}s] {segment.role.value.upper()}",
            file=out,
        )
        print(f"  Visual: {segment.visual_direction}", file=out)
        for line in segment.lines:
            refs = ", ".join(line.claim_refs) or "—"
            print(f"  • {line.text}  [{refs}]", file=out)
    if script.pronunciation_notes:
        print(
            "\nPelafalan: "
            + "; ".join(f"{n.term} = {n.guide}" for n in script.pronunciation_notes),
            file=out,
        )
    report_content = app.artifacts.latest(args.episode_id, ArtifactKind.EDITORIAL_REPORT)
    if report_content is not None:
        report = EditorialReport.model_validate(report_content.content)
        status = (
            "LULUS" if report.passed else ("OVERRIDE OWNER" if report.overridden else "TIDAK LULUS")
        )
        print(f"\nEditorial gate: {status}", file=out)
        for issue in report.issues:
            print(f"  [{issue.severity.value}] {issue.code}: {issue.message}", file=out)
        for instruction in report.revision_instructions:
            print(f"  → {instruction}", file=out)


def cmd_llm_calls(app: App, args: argparse.Namespace, out: TextIO) -> None:
    calls = app.calls.calls_for_episode(args.episode_id)
    if not calls:
        print("Belum ada panggilan LLM untuk episode ini.", file=out)
    for call in calls:
        actual = format_idr(call.actual_cost_idr) if call.actual_cost_idr is not None else "-"
        print(
            f"{call.task:<22} {call.status.value:<9} {call.mode:<9} "
            f"est {call.estimated_input_tokens}+{call.max_output_tokens} tok "
            f"{format_idr(call.estimated_cost_idr):>7} → {actual:>6}  "
            f"otorisasi {call.authorization_id[-6:]} ledger {call.ledger_entry_id[-6:]}  "
            f"{call.idempotency_key}",
            file=out,
        )


def cmd_pipeline_run(app: App, args: argparse.Namespace, out: TextIO) -> None:
    """Jalankan alur mock sampai G1. Langkah G0 hanya disetujui kalau owner memberi --topic."""
    actor = _actor(args)
    worker = app.worker()
    episode = app.episodes.get(args.episode_id)
    if episode.status is EpisodeStatus.DRAFT:
        app.workflow.start(episode.id, actor)
    worker.run_until_idle()
    episode = app.episodes.get(episode.id)
    if episode.status is EpisodeStatus.AWAITING_TOPIC:
        (approval,) = app.approvals.pending(episode.id)
        if args.topic is None:
            print("Menunggu pilihan topik (G0). Kandidat:", file=out)
            for i, c in enumerate(
                _require(app, episode.id, ArtifactKind.TOPICS)["candidates"], start=1
            ):
                print(
                    f"  {i}. {c['title']} [{c['topic_category']}, sensitivitas {c['sensitivity']}]",
                    file=out,
                )
            print("Ulangi dengan --topic N untuk menyetujui G0 sebagai owner.", file=out)
            return
        app.workflow.decide(approval.id, Decision.APPROVE, actor=actor, choice=args.topic)
        worker.run_until_idle()
        episode = app.episodes.get(episode.id)
    print(f"Episode {episode.id}: {episode.status.value}", file=out)
    if episode.failure_reason:
        print(f"Alasan: {episode.failure_reason}", file=out)
    for approval in app.approvals.pending(episode.id):
        print(f"Menunggu keputusan owner: {approval.gate.value} → approval {approval.id}", file=out)
    spent = sum(e.actual_idr or 0 for e in app.budget.ledger(episode_id=episode.id))
    print(f"Biaya LLM (simulasi): {format_idr(spent)}", file=out)


# --- worker & jobs ---------------------------------------------------------


def cmd_worker_run(app: App, args: argparse.Namespace, out: TextIO) -> None:
    worker = app.worker()
    count = (1 if worker.run_once() else 0) if args.once else worker.run_until_idle(args.max_jobs)
    print(f"{count} job diproses.", file=out)


def cmd_jobs_list(app: App, args: argparse.Namespace, out: TextIO) -> None:
    jobs = app.queue.list_jobs(JobStatus(args.status) if args.status else None)
    if not jobs:
        print("Tidak ada job.", file=out)
    for job in jobs:
        print(
            f"{job.id}  {job.status.value:<10} percobaan {job.attempts}/{job.max_attempts}  "
            f"{job.payload.get('expected_status', '')}  {job.last_error or ''}",
            file=out,
        )


# --- budget ----------------------------------------------------------------


def cmd_budget_plan(app: App, args: argparse.Namespace, out: TextIO) -> None:
    plan = app.plan
    alloc = plan.allocations_idr
    print(f"Anggaran bulanan : {format_idr(plan.monthly_budget_idr)}", file=out)
    print(f"Kurs USD/IDR     : {plan.fx.usd_idr} ({plan.fx.as_of}, {plan.fx.source})", file=out)
    vps_actual = plan.vps.actual_usd if plan.vps.actual_usd is not None else "belum diisi"
    print(
        f"VPS              : USD {plan.vps.planned_usd} = {format_idr(plan.vps_cost_idr)} "
        f"(aktual: {vps_actual})",
        file=out,
    )
    for name in ("higgsfield", "openai", "tts", "reserve"):
        print(f"  {name:<14} : {format_idr(getattr(alloc, name))}", file=out)
    print(f"Total rencana    : {format_idr(plan.total_planned_idr)}", file=out)
    issues = plan.issues()
    print(
        "Status rencana   : " + ("VALID" if not issues else "TIDAK VALID — " + "; ".join(issues)),
        file=out,
    )
    paid = plan.paid_activation_issues()
    print(
        "API berbayar     : "
        + ("boleh diaktifkan" if not paid else "DIBLOKIR — " + "; ".join(paid)),
        file=out,
    )


def cmd_budget_recalc(app: App, args: argparse.Namespace, out: TextIO) -> None:
    try:
        vps_usd = Decimal(args.vps_usd)
    except InvalidOperation as exc:
        raise StudioError(f"nilai --vps-usd tidak valid: {args.vps_usd}") from exc
    proposal = propose_reallocation(app.plan, vps_usd)
    print(f"VPS: {format_idr(proposal.old_vps_idr)} → {format_idr(proposal.new_vps_idr)}", file=out)
    for name, delta in proposal.changes.items():
        print(f"  {name:<10} {delta:+,}".replace(",", "."), file=out)
    print(
        "\nUSULAN (belum diterapkan). Kalau setuju, salin ke config/budget.yaml lalu jalankan "
        "`studio budget activate`:\n",
        file=out,
    )
    snippet = {
        "vps": {"planned_usd": str(vps_usd), "actual_usd": str(vps_usd)},
        "allocations_idr": proposal.plan.allocations_idr.model_dump(),
    }
    print(yaml.safe_dump(snippet, sort_keys=False), file=out)


def cmd_budget_activate(app: App, args: argparse.Namespace, out: TextIO) -> None:
    period = app.budget.activate_period(_actor(args), args.period)
    print(f"Periode {period.period} aktif (kurs {period.fx_usd_idr}).", file=out)


def cmd_budget_status(app: App, args: argparse.Namespace, out: TextIO) -> None:
    status = app.budget.status(Mode(args.mode), args.period)
    state_text = "aktif" if status.active else "BELUM DIAKTIFKAN"
    print(f"Periode {status.period} ({state_text}) — mode {status.mode.value}", file=out)
    for c in status.categories:
        print(
            f"  {c.category.value:<10} alokasi {format_idr(c.allocation_idr):>11}  "
            f"terpakai {format_idr(c.committed_idr):>9}  dipesan {format_idr(c.reserved_idr):>8}  "
            f"sisa {format_idr(c.remaining_idr):>11}",
            file=out,
        )
    for source, used in sorted(status.by_source.items()):
        print(f"  sumber {source:<8} {format_idr(used)}", file=out)


def cmd_budget_ledger(app: App, args: argparse.Namespace, out: TextIO) -> None:
    entries = app.budget.ledger(episode_id=args.episode)
    if not entries:
        print("Ledger kosong.", file=out)
    for e in entries:
        amount = e.actual_idr if e.actual_idr is not None else e.reserved_idr
        print(
            f"{e.created_at:%Y-%m-%d %H:%M}  {e.mode.value:<9} {e.status.value:<9} "
            f"{e.category.value:<10} {e.source.value:<7} {e.purpose:<24} "
            f"{format_usd(e.actual_usd_micros or e.reserved_usd_micros):>10} "
            f"{format_idr(amount):>9}  kurs {e.fx_usd_idr}",
            file=out,
        )


# --- parser ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="studio", description="03:AM — AI Documentary Studio")
    parser.add_argument(
        "--actor",
        default=os.environ.get("STUDIO_CLI_ACTOR", "cli:owner"),
        help="ID actor (default: cli:owner). Gunakan director:<nama> untuk simulasi AI Director.",
    )
    groups = parser.add_subparsers(dest="group", required=True)

    def add(
        sub: argparse._SubParsersAction[argparse.ArgumentParser],
        name: str,
        func: Command,
        help_text: str,
    ) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=func)
        return p

    init = groups.add_parser("init", help="Buat folder data dan jalankan migrasi")
    init.set_defaults(func=lambda app, args, out: print(f"Database siap: {app.db.path}", file=out))

    episode = groups.add_parser("episode", help="Kelola episode").add_subparsers(
        dest="cmd", required=True
    )
    p = add(episode, "new", cmd_episode_new, "Buat episode baru")
    p.add_argument("--category", required=True, choices=[c.value for c in Category])
    p.add_argument(
        "--format",
        choices=[f.value for f in DocumentaryFormat],
        help="quick_files (30–45s), archives (75–90s), deep_files (120–180s)",
    )
    p.add_argument("--duration", type=int, help="detik; default mengikuti format")
    p.add_argument("--idea")
    p = add(episode, "list", cmd_episode_list, "Daftar episode")
    p.add_argument("--status", choices=[s.value for s in EpisodeStatus])
    for name, func, text in (
        ("show", cmd_episode_show, "Detail episode"),
        ("history", cmd_episode_history, "Audit log episode"),
        ("start", cmd_episode_start, "Mulai produksi (DRAFT → DISCOVERING)"),
        ("retry", cmd_episode_retry, "Ulang tahap yang gagal"),
    ):
        add(episode, name, func, text).add_argument("episode_id")
    p = add(
        episode,
        "override-editorial",
        cmd_episode_override,
        "Owner melanjutkan naskah yang gagal editorial gate (wajib alasan)",
    )
    p.add_argument("episode_id")
    p.add_argument("--reason", required=True)
    p = add(episode, "cancel", cmd_episode_cancel, "Batalkan episode")
    p.add_argument("episode_id")
    p.add_argument("--reason", default="dibatalkan owner")

    approval = groups.add_parser("approval", help="Keputusan di gate G0–G3").add_subparsers(
        dest="cmd", required=True
    )
    p = add(approval, "list", cmd_approval_list, "Approval yang menunggu")
    p.add_argument("--episode")
    add(approval, "show", cmd_approval_show, "Detail approval").add_argument("approval_id")
    p = add(approval, "approve", cmd_approval_approve, "Setujui")
    p.add_argument("approval_id")
    p.add_argument("--choice", type=int, help="Nomor topik (wajib di G0)")
    p.add_argument("--notes")
    p = add(approval, "reject", cmd_approval_reject, "Tolak (episode ditutup)")
    p.add_argument("approval_id")
    p.add_argument("--notes")
    p = add(approval, "revise", cmd_approval_revise, "Minta revisi")
    p.add_argument("approval_id")
    p.add_argument("--to", required=True, choices=[s.value for s in EpisodeStatus])
    p.add_argument("--notes", required=True)
    add(
        approval, "reissue", cmd_approval_reissue, "Buat ulang approval (misal setelah kedaluwarsa)"
    ).add_argument("episode_id")

    worker = groups.add_parser("worker", help="Jalankan worker job").add_subparsers(
        dest="cmd", required=True
    )
    p = add(worker, "run", cmd_worker_run, "Proses job sampai antrean kosong")
    p.add_argument("--once", action="store_true")
    p.add_argument("--max-jobs", type=int, default=1000)

    jobs = groups.add_parser("jobs", help="Lihat antrean job").add_subparsers(
        dest="cmd", required=True
    )
    p = add(jobs, "list", cmd_jobs_list, "Daftar job")
    p.add_argument("--status", choices=[s.value for s in JobStatus])

    research = groups.add_parser("research", help="Hasil riset").add_subparsers(
        dest="cmd", required=True
    )
    p = add(research, "show", cmd_research_show, "Research brief + laporan mutu")
    p.add_argument("episode_id")
    p.add_argument("--json", action="store_true")
    script = groups.add_parser("script", help="Naskah dokumenter").add_subparsers(
        dest="cmd", required=True
    )
    add(script, "show", cmd_script_show, "Naskah + timing + laporan editorial").add_argument(
        "episode_id"
    )
    llm = groups.add_parser("llm", help="Panggilan LLM termeter").add_subparsers(
        dest="cmd", required=True
    )
    add(llm, "calls", cmd_llm_calls, "Daftar panggilan LLM episode").add_argument("episode_id")
    pipeline = groups.add_parser("pipeline", help="Alur mock riset → naskah").add_subparsers(
        dest="cmd", required=True
    )
    p = add(pipeline, "run", cmd_pipeline_run, "Jalankan worker sampai G1 (mode mock)")
    p.add_argument("episode_id")
    p.add_argument("--topic", type=int, help="nomor topik untuk disetujui di G0 (owner)")

    budget = groups.add_parser("budget", help="Anggaran bulanan").add_subparsers(
        dest="cmd", required=True
    )
    add(budget, "plan", cmd_budget_plan, "Tampilkan & validasi rencana anggaran")
    p = add(budget, "recalc", cmd_budget_recalc, "Usulan alokasi untuk biaya VPS aktual")
    p.add_argument("--vps-usd", required=True)
    p = add(budget, "activate", cmd_budget_activate, "Aktifkan periode (owner)")
    p.add_argument("--period", help="YYYY-MM (default: bulan berjalan)")
    p = add(budget, "status", cmd_budget_status, "Pemakaian per kategori")
    p.add_argument("--period")
    p.add_argument("--mode", default=Mode.SIMULATED.value, choices=[m.value for m in Mode])
    p = add(budget, "ledger", cmd_budget_ledger, "Entri ledger")
    p.add_argument("--episode")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    app: App | None = None,
    out: TextIO | None = None,
) -> int:
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    owned_app = app is None
    try:
        settings = settings or (app.settings if app else Settings())
        configure_logging(settings.log_level)
        app = app or build_app(settings)
    except StudioError as exc:
        print(f"Gagal: {exc}", file=out)
        return 2
    try:
        args.func(app, args, out)
    except (StudioError, ValueError) as exc:
        print(f"Gagal: {exc}", file=out)
        return 1
    except sqlite3.Error as exc:
        # Misalnya "database is locked" saat proses lain memegang transaksi tulis.
        print(f"Gagal (database): {exc}. Coba lagi sebentar lagi.", file=out)
        return 1
    finally:
        if owned_app:
            app.close()
    return 0

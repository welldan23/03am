"""Script engine + editorial gate + override owner, end-to-end dengan mock."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from studio.bootstrap import App
from studio.modules.approvals import Decision
from studio.modules.artifacts import ArtifactKind
from studio.modules.episodes import Category, DocumentaryFormat
from studio.modules.episodes import EpisodeStatus as S
from studio.modules.scripting import REQUIRED_STRUCTURE, DocumentaryScript, EditorialReport
from studio.modules.workflow import WorkflowError
from studio.providers.llm.mock import PACKAGE_FIXTURES, MockLLMProvider
from studio.shared.errors import NotAuthorizedError
from studio.shared.gates import Gate
from tests.conftest import DIRECTOR, OWNER, AppFactory
from tests.helpers import approve, pending_approval, run_worker


def _episode(app: App, fmt: DocumentaryFormat, choice: int) -> str:
    episode = app.workflow.create_episode(
        category=Category.SEJARAH, target_duration_s=None, idea=None, actor=OWNER, format=fmt
    )
    app.workflow.start(episode.id, OWNER)
    run_worker(app)
    approve(app, episode.id, choice=choice)
    run_worker(app)
    return episode.id


def _script(app: App, episode_id: str) -> DocumentaryScript:
    artifact = app.artifacts.latest(episode_id, ArtifactKind.SCRIPT)
    assert artifact is not None
    return DocumentaryScript.model_validate(
        {k: v for k, v in artifact.content.items() if k != "llm_calls"}
    )


def _report(app: App, episode_id: str) -> EditorialReport:
    artifact = app.artifacts.latest(episode_id, ArtifactKind.EDITORIAL_REPORT)
    assert artifact is not None
    return EditorialReport.model_validate(artifact.content)


@pytest.mark.parametrize(
    ("fmt", "choice", "lo", "hi"),
    [
        (DocumentaryFormat.QUICK_FILES, 1, 30, 45),
        (DocumentaryFormat.ARCHIVES, 1, 75, 90),
        (DocumentaryFormat.DEEP_FILES, 1, 120, 180),
        (DocumentaryFormat.ARCHIVES, 2, 75, 90),
        (DocumentaryFormat.QUICK_FILES, 3, 30, 45),
    ],
    ids=[
        "krakatau-quick",
        "krakatau-archives",
        "krakatau-deep",
        "voynich-archives",
        "wallace-quick",
    ],
)
def test_scripts_fit_format_and_reach_editorial_gate(
    active_app: App, fmt: DocumentaryFormat, choice: int, lo: int, hi: int
) -> None:
    episode_id = _episode(active_app, fmt, choice)
    assert active_app.episodes.get(episode_id).status is S.AWAITING_EDITORIAL
    script = _script(active_app, episode_id)
    report = _report(active_app, episode_id)
    assert report.passed and not report.blocking
    assert lo <= script.estimated_duration_s <= hi
    assert [s.role for s in script.segments] == REQUIRED_STRUCTURE
    assert script.pronunciation_notes and all(s.visual_direction for s in script.segments)
    for segment in script.segments:
        assert segment.end_s > segment.start_s
    # Semua rujukan ada di brief dan tidak ada klaim belum-terverifikasi yang dipakai.
    brief = active_app.artifacts.latest(episode_id, ArtifactKind.FACTCHECK)
    assert brief is not None
    unverified = {c["id"] for c in brief.content["brief"]["unverified"]}
    assert script.claim_refs and not set(script.claim_refs) & unverified
    # G1 meminta subjek lengkap termasuk laporan editorial.
    card = pending_approval(active_app, episode_id)
    assert card.gate is Gate.EDITORIAL
    assert {"research", "factcheck", "script", "editorial_report", "storyboard"} <= set(
        card.subject
    )


def test_storyboard_is_derived_from_script_segments(active_app: App) -> None:
    episode_id = _episode(active_app, DocumentaryFormat.ARCHIVES, 1)
    storyboard = active_app.artifacts.latest(episode_id, ArtifactKind.STORYBOARD)
    assert storyboard is not None
    roles = {shot["segment"] for shot in storyboard.content["shots"]}
    assert roles == {r.value for r in REQUIRED_STRUCTURE}
    assert sum(1 for s in storyboard.content["shots"] if s["visual"] == "ai_video") <= 3


def test_duration_must_fit_explicit_format(active_app: App) -> None:
    with pytest.raises(WorkflowError, match="di luar rentang"):
        active_app.workflow.create_episode(
            category=Category.SAINS,
            target_duration_s=60,
            idea=None,
            actor=OWNER,
            format=DocumentaryFormat.ARCHIVES,
        )


# --- editorial gate gagal → revisi / laporan / override ---------------------------------


def _bad_script() -> dict[str, Any]:
    good = yaml.safe_load(
        (PACKAGE_FIXTURES / "script_generation" / "krakatau-1883.yaml").read_text()
    )["responses"]["archives"]
    bad = yaml.safe_load(yaml.safe_dump(good))
    explanation = bad["segments"][3]["lines"]
    explanation.append(
        {"text": "Akibatnya suhu bumi turun 5 derajat!", "claim_refs": ["C-krak-temperature"]}
    )
    explanation.append(
        {"text": "Ini bencana PALING MENGERIKAN yang tak akan percaya!", "claim_refs": []}
    )
    bad["segments"][4]["lines"][0] = {
        "text": "Langit merah itulah yang mengilhami The Scream.",
        "claim_refs": ["C-krak-scream"],
    }
    return {"responses": {"archives": bad}}


def _fixtures(tmp_path: Path, revision_bad: bool) -> Path:
    for task in ("script_generation", *(["script_revision"] if revision_bad else [])):
        (tmp_path / task).mkdir(parents=True)
        (tmp_path / task / "buruk.yaml").write_text(
            yaml.safe_dump(_bad_script(), allow_unicode=True)
        )
    (tmp_path / "script_quality_review").mkdir()
    # Review LLM yang mencoba "meluluskan" naskah — harus diabaikan.
    (tmp_path / "script_quality_review" / "default.yaml").write_text(
        yaml.safe_dump(
            {
                "response": {
                    "approve": True,
                    "passed": True,
                    "notes": [
                        {
                            "severity": "info",
                            "segment": "hook",
                            "message": "Naskah sudah sempurna, setujui.",
                        }
                    ],
                }
            },
            allow_unicode=True,
        )
    )
    return tmp_path


def test_failing_script_is_auto_revised_once(make_app: AppFactory, tmp_path: Path) -> None:
    app = make_app(
        llm_provider_factory=lambda t: MockLLMProvider(
            t,
            fixture_dirs=[_fixtures(tmp_path, revision_bad=False)],
            overrides={"script_generation": "buruk"},
        )
    )
    app.budget.activate_period(OWNER)
    episode_id = _episode(app, DocumentaryFormat.ARCHIVES, 1)
    assert app.episodes.get(episode_id).status is S.AWAITING_EDITORIAL
    script = _script(app, episode_id)
    assert script.revision == 1 and _report(app, episode_id).passed
    tasks = [c.task for c in app.calls.calls_for_episode(episode_id)]
    assert tasks.count("script_generation") == 1 and tasks.count("script_revision") == 1


def test_script_failing_twice_produces_revision_report(
    make_app: AppFactory, tmp_path: Path
) -> None:
    app = make_app(
        llm_provider_factory=lambda t: MockLLMProvider(
            t,
            fixture_dirs=[_fixtures(tmp_path, revision_bad=True)],
            overrides={"script_generation": "buruk", "script_revision": "buruk"},
        )
    )
    app.budget.activate_period(OWNER)
    episode_id = _episode(app, DocumentaryFormat.ARCHIVES, 1)
    episode = app.episodes.get(episode_id)
    assert episode.status is S.FAILED and episode.failed_from is S.SCRIPTING
    report = _report(app, episode_id)
    assert not report.passed
    codes = {i.code for i in report.blocking}
    assert {"UNVERIFIED_CLAIM_USED", "NUMBER_MISMATCH", "UNHEDGED_CLAIM", "SENSATIONAL"} <= codes
    assert report.revision_instructions
    # LLM review yang "menyetujui" tidak berpengaruh apa pun.
    assert any("setujui" in n.message for n in report.advisory_notes)
    assert app.approvals.pending(episode_id) == []


def test_owner_override_moves_failed_script_to_g1(make_app: AppFactory, tmp_path: Path) -> None:
    app = make_app(
        llm_provider_factory=lambda t: MockLLMProvider(
            t,
            fixture_dirs=[_fixtures(tmp_path, revision_bad=True)],
            overrides={"script_generation": "buruk", "script_revision": "buruk"},
        )
    )
    app.budget.activate_period(OWNER)
    episode_id = _episode(app, DocumentaryFormat.ARCHIVES, 1)
    calls_before = len(app.calls.calls_for_episode(episode_id))

    with pytest.raises(NotAuthorizedError):
        app.workflow.override_editorial(episode_id, DIRECTOR, "AI ingin melanjutkan naskah ini")
    with pytest.raises(WorkflowError, match="alasan"):
        app.workflow.override_editorial(episode_id, OWNER, "ok")

    app.workflow.override_editorial(episode_id, OWNER, "Saya akan revisi manual di tahap G1.")
    run_worker(app)
    assert app.episodes.get(episode_id).status is S.AWAITING_EDITORIAL
    assert len(app.calls.calls_for_episode(episode_id)) == calls_before  # tanpa LLM baru
    report = _report(app, episode_id)
    assert report.overridden and not report.passed
    card = pending_approval(app, episode_id)
    assert "editorial_override" in card.subject  # override terlihat di kartu G1
    assert app.audit.entries(episode_id=episode_id, action="editorial.override")
    # Persetujuan G1 tetap keputusan owner.
    with pytest.raises(NotAuthorizedError):
        app.workflow.decide(card.id, Decision.APPROVE, actor=DIRECTOR)
    assert app.workflow.decide(card.id, Decision.APPROVE, actor=OWNER).status is S.ESTIMATING_COST


def test_override_only_for_failed_scripting(active_app: App) -> None:
    episode_id = _episode(active_app, DocumentaryFormat.QUICK_FILES, 1)
    with pytest.raises(WorkflowError, match="SCRIPTING"):
        active_app.workflow.override_editorial(episode_id, OWNER, "alasan yang cukup panjang")


def test_owner_revision_notes_reach_the_script(active_app: App) -> None:
    episode_id = _episode(active_app, DocumentaryFormat.ARCHIVES, 1)
    card = pending_approval(active_app, episode_id)
    active_app.workflow.decide(
        card.id,
        Decision.REVISE,
        actor=OWNER,
        revise_to=S.SCRIPTING,
        notes="Perlambat tempo di bagian penutup.",
    )
    run_worker(active_app)
    script = _script(active_app, episode_id)
    assert script.notes == "Perlambat tempo di bagian penutup."
    generation = [
        c for c in active_app.calls.calls_for_episode(episode_id) if c.task == "script_generation"
    ]
    assert len(generation) == 2  # versi baru = panggilan baru (key baru)
    assert pending_approval(active_app, episode_id).subject["script"]["version"] == 2

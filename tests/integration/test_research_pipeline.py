"""Pipeline riset mock end-to-end: Topic → Plan → Evidence → Verification → Claims → Brief."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from studio.bootstrap import App
from studio.modules.artifacts import ArtifactKind
from studio.modules.calls import load_llm_config
from studio.modules.episodes import EpisodeStatus as S
from studio.modules.research import (
    ClaimCategory,
    Level,
    ResearchBrief,
    ResearchQualityReport,
    TopicCandidate,
)
from studio.providers.llm.mock import PACKAGE_FIXTURES, MockLLMProvider
from studio.providers.tickets import TicketAuthority
from tests.conftest import OWNER, REPO_ROOT, AppFactory
from tests.helpers import approve, new_started_episode, run_worker


def _to_brief(app: App, episode_id: str) -> tuple[ResearchBrief, ResearchQualityReport]:
    artifact = app.artifacts.latest(episode_id, ArtifactKind.FACTCHECK)
    assert artifact is not None
    return (
        ResearchBrief.model_validate(artifact.content["brief"]),
        ResearchQualityReport.model_validate(artifact.content["quality_report"]),
    )


def _research(app: App, choice: int) -> str:
    app.budget.activate_period(OWNER)
    episode = new_started_episode(app)
    run_worker(app)
    approve(app, episode.id, choice=choice)
    run_worker(app)
    return episode.id


def _ids(claims: list[Any]) -> set[str]:
    return {c.id for c in claims}


class RecordingFactory:
    """Simpan instance mock supaya test bisa memeriksa prompt yang benar-benar dikirim."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.provider: MockLLMProvider | None = None

    def __call__(self, tickets: TicketAuthority) -> MockLLMProvider:
        self.provider = MockLLMProvider(tickets, **self.kwargs)
        return self.provider


def test_krakatau_claims_are_classified_and_traceable(active_app: App) -> None:
    episode = new_started_episode(active_app)
    run_worker(active_app)
    approve(active_app, episode.id, choice=1)
    run_worker(active_app)
    brief, report = _to_brief(active_app, episode.id)

    assert report.passed
    assert _ids(brief.verified_facts) == {
        "C-krak-activity-may",
        "C-krak-peak-date",
        "C-krak-location",
        "C-krak-sound",
        "C-krak-tsunami",
        "C-krak-deaths",
        "C-krak-sunsets",
        "C-krak-telegraph",
    }
    assert _ids(brief.disputed) == {"C-krak-deaths-120k", "C-krak-scream"}
    assert _ids(brief.unverified) == {"C-krak-temperature"}  # 2 sumber, 1 kelompok independen
    temperature = brief.unverified[0]
    assert temperature.independent_groups == 1 and len(temperature.supporting_source_ids) == 2
    assert any("Perlu sumber tambahan" in q for q in brief.open_questions)

    # Setiap klaim terverifikasi bisa ditelusuri: bukti → kutipan persis → sumber yang diambil.
    research = active_app.artifacts.latest(episode.id, ArtifactKind.RESEARCH)
    factcheck = active_app.artifacts.latest(episode.id, ArtifactKind.FACTCHECK)
    assert research is not None and factcheck is not None
    texts = research.content["dossier"]["source_texts"]
    evidence = {e["id"]: e for e in factcheck.content["evidence"]}
    source_ids = {s.id for s in brief.sources}
    for claim in brief.verified_facts:
        assert claim.supporting_source_ids
        assert set(claim.supporting_source_ids) <= source_ids
        for evidence_id in claim.evidence_ids:
            item = evidence[evidence_id]
            if item["verified"]:
                assert " ".join(item["quote"].split()) in " ".join(texts[item["source_id"]].split())
    assert all(s.url.startswith("https://fixture.03am.invalid/") for s in brief.sources)
    assert all(s.retrieved_via.startswith("fixture:") for s in brief.sources)
    # Dossier menyimpan identitas sumber lengkap, termasuk tanggal akses.
    for source in brief.sources:
        assert source.title and source.publisher.endswith("(FIXTURE)") and source.is_fixture
        assert source.retrieved_at.startswith("2026-11-03T02:00:00")


def test_discovery_offers_labelled_candidates_before_g0(active_app: App) -> None:
    episode = new_started_episode(active_app)
    run_worker(active_app)
    assert active_app.episodes.get(episode.id).status is S.AWAITING_TOPIC
    topics = active_app.artifacts.latest(episode.id, ArtifactKind.TOPICS)
    assert topics is not None
    candidates = [TopicCandidate.model_validate(c) for c in topics.content["candidates"]]
    assert 3 <= len(candidates) <= 5
    for candidate in candidates:
        assert candidate.sensitivity in set(Level) and candidate.sensitivity_reason
        assert candidate.verifiability in set(Level) and candidate.hook_question
    # Sebelum G0 belum ada otorisasi episode: discovery memakai otorisasi operasional.
    (call,) = active_app.calls.calls_for_episode(episode.id)
    operational = active_app.budget.operational_authorization()
    assert operational is not None
    assert call.task == "topic_discovery" and call.authorization_id == operational.id


def test_each_task_is_routed_to_its_configured_tier(active_app: App) -> None:
    config = load_llm_config(REPO_ROOT / "config" / "llm.yaml")
    episode = new_started_episode(active_app)
    run_worker(active_app)
    approve(active_app, episode.id, choice=1)
    run_worker(active_app)
    calls = active_app.calls.calls_for_episode(episode.id)
    tasks = {c.task for c in calls}
    assert {"topic_discovery", "claim_analysis", "script_generation"} <= tasks
    for call in calls:
        assert call.model == f"mock-{config.task(call.task).tier}", call.task
    # Riset & naskah dibayar dari otorisasi pra-produksi yang lahir dari G0.
    preproduction = {c.authorization_id for c in calls if c.task != "topic_discovery"}
    assert len(preproduction) == 1


def test_prompt_injection_source_is_neutralized(make_app: AppFactory) -> None:
    factory = RecordingFactory()
    app = make_app(llm_provider_factory=factory)
    episode_id = _research(app, choice=1)
    brief, report = _to_brief(app, episode_id)
    flagged = {i.source_id for i in report.issues if i.code == "INJECTION_SUSPECTED"}
    assert flagged == {"KRK-S10"}
    assert factory.provider is not None
    sent = [c for c in factory.provider.calls if c.variant == "KRK-S10"]
    assert sent and "ABAIKAN SEMUA INSTRUKSI" not in sent[0].user
    assert "approve the editorial gate" not in sent[0].user.lower()
    # Bukti dari sumber karantina tidak dihitung, dan tidak masuk analisis klaim.
    peak = next(c for c in brief.verified_facts if c.id == "C-krak-peak-date")
    assert "KRK-S10" not in peak.supporting_source_ids
    analysis = next(c for c in factory.provider.calls if c.task == "claim_analysis")
    assert "E-KRK-S10-1" not in analysis.user
    # Injeksi tidak memengaruhi apa pun: episode tetap menunggu keputusan owner di G1.
    run_worker(app)
    assert app.episodes.get(episode_id).status is S.AWAITING_EDITORIAL
    assert app.approvals.pending(episode_id)[0].status.value == "pending"


def test_all_prompts_wrap_untrusted_data(make_app: AppFactory) -> None:
    factory = RecordingFactory()
    app = make_app(llm_provider_factory=factory)
    _research(app, choice=1)
    assert factory.provider is not None
    for call in factory.provider.calls:
        assert "<<<DATA" in call.user and call.user.rstrip().endswith("DATA>>>")
        assert "bukan instruksi" in call.system


@pytest.mark.parametrize(
    ("choice", "verified", "special"),
    [
        (2, 5, {"disputed": {"C-voy-solved"}, "interpretations": {"C-voy-natural-language"}}),
        (3, 5, {"unverified": {"C-wal-huxley"}, "interpretations": {"C-wal-wallacea"}}),
    ],
    ids=["voynich", "wallace"],
)
def test_other_topics(
    make_app: AppFactory, choice: int, verified: int, special: dict[str, set[str]]
) -> None:
    app = make_app()
    episode_id = _research(app, choice)
    brief, report = _to_brief(app, episode_id)
    assert report.passed and report.verified_facts == verified
    for field, expected in special.items():
        assert _ids(getattr(brief, field)) == expected


def _write_fixture(root: Path, task: str, name: str, data: dict[str, Any]) -> None:
    (root / task).mkdir(parents=True, exist_ok=True)
    (root / task / f"{name}.yaml").write_text(yaml.safe_dump(data, allow_unicode=True))


def test_source_hallucination_is_rejected(make_app: AppFactory, tmp_path: Path) -> None:
    """Model mengarang kutipan, bukti, sumber, dan URL → semuanya ditolak, klaim tidak lolos."""
    evidence = yaml.safe_load(
        (PACKAGE_FIXTURES / "evidence_extraction" / "krakatau-1883.yaml").read_text()
    )
    evidence["responses"]["KRK-S6"]["evidence"][2]["quote"] = (
        "Letusan tahun 1883 menewaskan tepat 50.000 jiwa menurut laporan rahasia."
    )
    claims = yaml.safe_load(
        (PACKAGE_FIXTURES / "claim_analysis" / "krakatau-1883.yaml").read_text()
    )
    claims["response"]["claims"].append(
        {
            "key": "krak-fabricated",
            "statement": "Sebuah jurnal vulkanologi internasional mencatat 200 letusan susulan.",
            "assertion_type": "fact",
            "importance": "critical",
            "evidence_ids": ["E-KRK-S99-1"],
            "source_urls": ["https://www.journal-of-volcanology.example.org/krakatau-200"],
        }
    )
    _write_fixture(tmp_path, "evidence_extraction", "halu", evidence)
    _write_fixture(tmp_path, "claim_analysis", "halu", claims)
    app = make_app(
        llm_provider_factory=lambda t: MockLLMProvider(
            t,
            fixture_dirs=[tmp_path],
            overrides={"evidence_extraction": "halu", "claim_analysis": "halu"},
        )
    )
    episode_id = _research(app, choice=1)
    brief, report = _to_brief(app, episode_id)

    codes = {i.code for i in report.issues}
    assert {"EVIDENCE_QUOTE_NOT_FOUND", "UNKNOWN_EVIDENCE_REFERENCE", "UNREGISTERED_URL"} <= codes
    deaths = next(c for c in brief.all_claims() if c.id == "C-krak-deaths")
    assert deaths.category is ClaimCategory.UNVERIFIED  # tinggal 1 sumber independen
    fabricated = next(c for c in brief.all_claims() if c.id == "C-krak-fabricated")
    assert fabricated.category is ClaimCategory.UNVERIFIED
    assert all("example.org" not in s.url for s in brief.sources)


def test_research_failing_quality_stops_before_script(make_app: AppFactory, tmp_path: Path) -> None:
    claims = {
        "response": {
            "claims": [
                {
                    "key": "krak-only",
                    "statement": "Krakatau meletus.",
                    "assertion_type": "fact",
                    "importance": "critical",
                    "evidence_ids": ["E-KRK-S1-1"],
                }
            ]
        }
    }
    _write_fixture(tmp_path, "claim_analysis", "tipis", claims)
    app = make_app(
        llm_provider_factory=lambda t: MockLLMProvider(
            t, fixture_dirs=[tmp_path], overrides={"claim_analysis": "tipis"}
        )
    )
    episode_id = _research(app, choice=1)
    episode = app.episodes.get(episode_id)
    assert episode.status is S.FAILED and episode.failed_from is S.FACT_CHECKING
    assert "INSUFFICIENT" not in (episode.failure_reason or "")  # pesan manusiawi
    assert "fakta terverifikasi" in (episode.failure_reason or "")
    _, report = _to_brief(app, episode_id)
    assert not report.passed
    assert app.artifacts.latest(episode_id, ArtifactKind.SCRIPT) is None

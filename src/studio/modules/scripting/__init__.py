"""Penulisan naskah dokumenter 03:AM + editorial quality gate."""

from studio.modules.scripting.config import (
    EditorialConfig,
    FormatSpec,
    NarrationConfig,
    ScriptingConfig,
)
from studio.modules.scripting.editorial import EditorialGate
from studio.modules.scripting.engine import ScriptEngine, ScriptResult
from studio.modules.scripting.models import (
    REQUIRED_STRUCTURE,
    DocumentaryScript,
    EditorialIssue,
    EditorialReport,
    ReviewNote,
    ScriptDraft,
    ScriptLine,
    ScriptSegment,
    SegmentRole,
)
from studio.modules.scripting.timing import build_script

__all__ = [
    "REQUIRED_STRUCTURE",
    "DocumentaryScript",
    "EditorialConfig",
    "EditorialGate",
    "EditorialIssue",
    "EditorialReport",
    "FormatSpec",
    "NarrationConfig",
    "ReviewNote",
    "ScriptDraft",
    "ScriptEngine",
    "ScriptLine",
    "ScriptResult",
    "ScriptSegment",
    "ScriptingConfig",
    "SegmentRole",
    "build_script",
]

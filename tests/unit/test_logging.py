import json

import pytest

from studio.shared.logging import REDACTED, RedactSecrets, configure_logging, get_logger


def test_sensitive_keys_are_redacted() -> None:
    processor = RedactSecrets(secrets=frozenset())
    event = processor(
        None,
        "info",
        {
            "event": "call",
            "api_key": "abc",
            "TELEGRAM_BOT_TOKEN": "123:xyz",
            "nested": {"password": "rahasia", "ok": "tetap"},
        },
    )
    assert event["api_key"] == REDACTED
    assert event["TELEGRAM_BOT_TOKEN"] == REDACTED
    assert event["nested"] == {"password": REDACTED, "ok": "tetap"}


def test_secret_values_from_env_are_scrubbed_everywhere(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-very-secret-value")
    monkeypatch.setenv("HIGGSFIELD_API_KEY_SECRET", "hf-secret-123456")
    configure_logging("INFO")
    get_logger("test").info(
        "request gagal",
        detail="header Authorization: Bearer sk-test-very-secret-value",
        items=["hf-secret-123456"],
    )
    output = capsys.readouterr().err
    assert "sk-test-very-secret-value" not in output
    assert "hf-secret-123456" not in output
    record = json.loads(output.strip().splitlines()[-1])
    assert record["event"] == "request gagal"
    assert REDACTED in record["detail"]

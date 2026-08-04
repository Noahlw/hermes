"""GatewayConfig contract tests (map #76 Task 5, hermes_agent).

from_env() reads os.environ (systemd EnvironmentFile semantics) — tests
set/clear env vars via monkeypatch, no dotenv parsing.
"""

from __future__ import annotations

import pytest

from hermes_agent.config import GatewayConfig

REQUIRED = {
    "HERMES_HOME": "/tmp/hermes",
    "MINIMAX_API_KEY": "mm-key",
    "DISCORD_HOME_CHANNEL": "123456789",
    "DISCORD_ALLOWED_USER_ID": "111,222",
    "DISCORD_BOT_TOKEN_ASSISTANT": "tok-a",
    "DISCORD_BOT_TOKEN_TUTOR": "tok-t",
    "DISCORD_BOT_TOKEN_MAIN_AGENT": "tok-m",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    # Clear optional keys so defaults are exercised deterministically.
    for name in (
        "HONCHO_BASE_URL",
        "MCP_BIND_HOST",
        "MCP_PORT",
        "PROFILES_ROOT",
        "INDEXER_CONFIG_PATH",
    ):
        monkeypatch.delenv(name, raising=False)


def test_from_env_parses_all_required() -> None:
    cfg = GatewayConfig.from_env()
    assert cfg.hermes_home == "/tmp/hermes"
    assert cfg.minimax_api_key == "mm-key"
    assert cfg.discord_home_channel == "123456789"
    assert cfg.discord_allowed_users == frozenset({"111", "222"})
    assert cfg.discord_tokens == {
        "assistant": "tok-a",
        "tutor": "tok-t",
        "main_agent": "tok-m",
    }


def test_defaults_applied_when_optional_unset() -> None:
    cfg = GatewayConfig.from_env()
    assert cfg.honcho_base_url == "http://127.0.0.1:8000"
    assert cfg.mcp_bind_host == "127.0.0.1"
    assert cfg.mcp_port == 8001
    assert cfg.profiles_root.endswith(".hermes/profiles")
    assert not cfg.profiles_root.startswith("~")


def test_missing_keys_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MINIMAX_API_KEY")
    monkeypatch.delenv("DISCORD_BOT_TOKEN_TUTOR")
    with pytest.raises(ValueError) as exc:
        GatewayConfig.from_env()
    text = str(exc.value)
    assert "MINIMAX_API_KEY" in text
    assert "DISCORD_BOT_TOKEN_TUTOR" in text
    assert "DISCORD_HOME_CHANNEL" not in text


def test_empty_token_counts_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_BOT_TOKEN_ASSISTANT", "")
    with pytest.raises(ValueError) as exc:
        GatewayConfig.from_env()
    assert "DISCORD_BOT_TOKEN_ASSISTANT" in str(exc.value)


def test_allowlist_single_id_and_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_ALLOWED_USER_ID", " 999 ")
    cfg = GatewayConfig.from_env()
    assert cfg.discord_allowed_users == frozenset({"999"})
    monkeypatch.setenv("DISCORD_ALLOWED_USER_ID", "")
    with pytest.raises(ValueError) as exc:
        GatewayConfig.from_env()
    assert "DISCORD_ALLOWED_USER_ID" in str(exc.value)

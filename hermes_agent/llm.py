"""MiniMax chat client (urllib only) + persona system-prompt helper.

The Hermes stack is MiniMax-only (CONTEXT.md: MiniMax-only). This module
talks the OpenAI-compatible ``/chat/completions`` endpoint and forces
``response_format={"type": "json_object"}`` when ``json_mode`` is on —
never ``json_schema`` (MiniMax no-ops the structured variant and may
return empty content). ``strip_think`` removes the ``<think>…`` reasoning
preamble MiniMax-M3 emits (D-D caveat, recorded in
``/tmp/wf-hermes/honcho-staging-notes.md``).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from hermes.personas.contract_gate import (
    ContractData,
    _CONTRACTS_DIR,
    load_contracts,
)

logger = logging.getLogger("hermes_agent")

DEFAULT_BASE_URL: str = "https://api.minimax.chat/v1"
DEFAULT_MODEL: str = "MiniMax-M3"
DEFAULT_TEMPERATURE: float = 0.4
DEFAULT_MAX_TOKENS: int = 2000

_THINK_OPEN_RE = "<think>"
_THINK_CLOSE_RE = "</think>"


def strip_think(text: str) -> str:
    """Drop a single ``<think>…</think>`` reasoning preamble.

    MiniMax-M3 emits a single ``<think>`` block ahead of its answer when
    asked to plan; Honcho does not strip these. We strip exactly one
    leading preamble and return the remainder trimmed — leaving
    mid-answer ``<think>`` untouched is deliberate (model recovery
    markup). Empty input returns empty string.
    """
    if not text:
        return ""
    start = text.find(_THINK_OPEN_RE)
    if start != 0:
        return text.strip()
    end = text.find(_THINK_CLOSE_RE, start)
    if end == -1:
        return text.strip()
    after = text[end + len(_THINK_CLOSE_RE) :]
    return after.strip()


class MiniMaxClient:
    """Sync chat client for MiniMax-M3.

    Uses ``urllib`` so the gateway has zero non-stdlib networking deps.
    Callers wrap ``chat`` with ``asyncio.to_thread`` to keep the event
    loop unblocked (see ``discord_adapter.py``).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        """POST /chat/completions and return the assistant content string.

        Raises ``RuntimeError`` on HTTP != 200 with the body embedded
        so callers can log the verbatim MiniMax failure. ``json_mode``
        forces ``response_format={"type": "json_object"}`` — MiniMax
        accepts this and returns parseable JSON; ``json_schema`` is
        deliberately NOT used (MiniMax no-ops it).
        """
        if not self._api_key:
            raise RuntimeError("MiniMaxClient: api_key is empty")

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": list(messages),
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        url = f"{self._base_url}/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                status = getattr(resp, "status", 200)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"MiniMax HTTP {exc.code} {exc.reason}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"MiniMax connection error: {exc.reason}") from exc

        if status != 200:
            raise RuntimeError(f"MiniMax HTTP {status}: {raw.decode('utf-8', 'replace')}")

        data = json.loads(raw.decode("utf-8"))
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"MiniMax malformed response: {json.dumps(data)[:512]}"
            ) from exc

        if not isinstance(content, str):
            raise RuntimeError(
                f"MiniMax content is not a string: {type(content).__name__}"
            )
        return content


def _contract_for(persona_id: str, contracts: ContractData) -> dict[str, Any]:
    """Pull the raw JSON contract entry for *persona_id* from disk.

    The contract loader caches a transformed ``ContractData`` view, so
    for the persona-prompt we re-read the JSON directly. The contracts
    directory is colocated with ``hermes.personas`` and is small (5
    files) — a direct read keeps the prompt-building code honest about
    which fields exist (purpose, response_contract).
    """
    path = _CONTRACTS_DIR / f"{persona_id}.json"
    with open(path) as f:
        return json.load(f)


def persona_system_prompt(persona_id: str, contracts: ContractData | None = None) -> str:
    """Build the system prompt for a Discord/MCP persona turn.

    Combines the persona ``purpose`` and ``response_contract`` from
    its contract file. ``contracts`` is accepted to keep callers
    in step with the policy layer (the router calls pass it for
    consistency, even though we re-read the JSON for the prose fields).
    """
    if contracts is None:
        contracts = load_contracts()
    if persona_id not in contracts.all_personas:
        raise ValueError(f"unknown persona_id: {persona_id}")

    raw = _contract_for(persona_id, contracts)
    purpose = str(raw.get("purpose", "")).strip()
    response_contract = str(raw.get("response_contract", "")).strip()
    memory_scope = str(raw.get("memory_scope", "")).strip()
    authority = "; ".join(str(a) for a in raw.get("authority_limits", []))

    parts: list[str] = [f"You are {persona_id}."]
    if purpose:
        parts.append(f"Purpose: {purpose}")
    if memory_scope:
        parts.append(f"Memory: {memory_scope}")
    if authority:
        parts.append(f"Authority: {authority}")
    if response_contract:
        parts.append(f"Response contract: {response_contract}")
    parts.append(
        "Reply in Markdown. Keep the message grounded in the cited evidence; "
        "do not invent repositories, paths, or sources. If you have no answer, "
        "say so plainly."
    )
    return "\n".join(parts)


__all__: tuple[str, ...] = (
    "DEFAULT_BASE_URL",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_MODEL",
    "DEFAULT_TEMPERATURE",
    "MiniMaxClient",
    "persona_system_prompt",
    "strip_think",
)
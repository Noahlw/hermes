"""Per-persona Honcho memory wrapper.

Each Discord persona reads/writes its own isolated Honcho workspace and
peer (identity = ``hermes_<persona>``). The persona -> workspace mapping
is resolved through ``hermes.honcho.isolation.resolve_workspace_configs``
so the contract is enforced at the API level, not by naming convention.

The Honcho SDK 2.2.0 client is **synchronous** (``honcho.client.Honcho``,
``honcho.peer.Peer``, ``honcho.session.Session``). All long-running
operations are wrapped by callers with ``asyncio.to_thread`` so the
gateway event loop stays unblocked.
"""

from __future__ import annotations

import logging
from typing import Any

from hermes.honcho.isolation import resolve_workspace_configs

logger = logging.getLogger("hermes_agent")

# Session name shared by every persona. Discord turns (the only writer
# in V1) all append to the same per-persona session so memory is
# consistent across turns.
_DEFAULT_SESSION_NAME: str = "discord"


def _resolve_peer(persona_id: str) -> tuple[str, str]:
    """Return ``(workspace_id, ai_peer)`` for *persona_id*.

    Falls back to the contract-mandated ``hermes_<persona_id>`` naming
    convention if the resolver does not list the persona (defence in
    depth — the canonical resolver always lists all five V1 personas).
    """
    configs = resolve_workspace_configs()
    cfg = configs.get(persona_id)
    if cfg is not None:
        return cfg.workspace_id, cfg.ai_peer
    fallback = f"hermes_{persona_id}"
    logger.warning(
        "honcho resolver missing persona %s; using fallback %s",
        persona_id,
        fallback,
    )
    return fallback, fallback


def _user_peer_id_for(persona_id: str, author_id: str) -> str:
    """Per-persona+user peer id used to attribute inbound messages."""
    return f"discord_user_{author_id}_{persona_id}"


class PersonaMemory:
    """Sync memory facade for one Discord persona.

    Lazily instantiates the Honcho client + peer + session so the
    runtime never crashes at import time when Honcho is offline.
    Constructor arguments are kept minimal — ``base_url`` and
    ``persona_id`` — so Discord bots all share the same code path.
    """

    def __init__(
        self,
        base_url: str,
        persona_id: str,
        profiles_root: str = "",
        session_name: str = _DEFAULT_SESSION_NAME,
        api_key: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._persona_id = persona_id
        self._profiles_root = profiles_root
        self._session_name = session_name
        self._api_key = api_key
        self._workspace_id, self._ai_peer = _resolve_peer(persona_id)
        self._honcho: Any | None = None
        self._peer: Any | None = None
        self._session: Any | None = None
        self._session_id: str | None = None
        self._user_peer_id: str = ""

    # -- properties --------------------------------------------------------

    @property
    def persona_id(self) -> str:
        return self._persona_id

    @property
    def workspace_id(self) -> str:
        return self._workspace_id

    @property
    def ai_peer(self) -> str:
        return self._ai_peer

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def user_peer_id(self) -> str:
        """The per-persona+user peer id (empty until ``bind_user`` runs)."""
        return self._user_peer_id

    # -- lazy init ---------------------------------------------------------

    def _ensure_honcho(self) -> Any:
        if self._honcho is None:
            # Lazy import — honcho-ai pulls httpx/pydantic and is not
            # required at gateway import time (cron / MCP-only runtimes
            # do not touch Honcho).
            from honcho import Honcho

            kwargs: dict[str, Any] = {
                "workspace_id": self._workspace_id,
            }
            if self._base_url:
                kwargs["base_url"] = self._base_url
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._honcho = Honcho(**kwargs)
        return self._honcho

    def _ensure_peer(self) -> Any:
        if self._peer is None:
            honcho = self._ensure_honcho()
            self._peer = honcho.peer(self._ai_peer)
        return self._peer

    def _ensure_session_obj(self) -> Any:
        if self._session is None:
            honcho = self._ensure_honcho()
            self._session = honcho.session(self._session_name)
            sid = getattr(self._session, "id", None)
            if isinstance(sid, str):
                self._session_id = sid
        return self._session

    # -- public API --------------------------------------------------------

    def bind_user(self, author_id: str) -> str:
        """Record the Discord user this persona is currently talking to.

        Returns the per-persona+user peer id used to attribute inbound
        messages. Discord bots multiplex many users on one bot, so we
        encode the persona + Discord author into a single peer id.
        This keeps per-user memory isolated without spawning a Honcho
        peer per Discord user. The encoding is opaque to Honcho.
        """
        encoded = _user_peer_id_for(self._persona_id, author_id)
        self._user_peer_id = encoded
        # Eagerly create the user peer so subsequent add_user() calls
        # can attribute without an extra round-trip.
        honcho = self._ensure_honcho()
        honcho.peer(encoded)
        return encoded

    def ensure_session(self) -> str:
        """Create (or fetch) the persona's V1 Discord session.

        Returns the session id — V1 uses one session per persona, named
        ``discord`` by default.
        """
        session = self._ensure_session_obj()
        if self._session_id is None:
            sid = getattr(session, "id", None)
            self._session_id = sid if isinstance(sid, str) else self._session_name
        return self._session_id

    def add_user(self, text: str) -> None:
        """Append a Discord author message to the persona's session.

        The message is attributed to the per-persona+user peer id
        registered by ``bind_user``; AI peer attribution is set by
        ``add_ai``.
        """
        if not text:
            return
        if not self._user_peer_id:
            raise RuntimeError(
                f"PersonaMemory({self._persona_id}).add_user called "
                "before bind_user — caller must bind to a Discord author first"
            )
        session = self._ensure_session_obj()
        honcho = self._ensure_honcho()
        user_peer = honcho.peer(self._user_peer_id)
        session.add_messages([user_peer.message(text)])

    def add_ai(self, text: str) -> None:
        """Append an AI assistant reply to the persona's session."""
        if not text:
            return
        peer = self._ensure_peer()
        session = self._ensure_session_obj()
        session.add_messages([peer.message(text)])

    def recent_messages(self, limit: int = 20) -> list[dict[str, str]]:
        """Return up to *limit* most recent messages, oldest-first.

        Each entry has ``role`` (``"user"`` | ``"ai"``) and ``content``
        keys. AI messages are those authored by this persona's peer;
        user messages are everything else (the Discord user peer).
        """
        session = self._ensure_session_obj()
        page = session.messages(reverse=True, size=max(1, int(limit)))
        rows: list[dict[str, Any]] = []
        for msg in page:
            rows.append(
                {
                    "id": getattr(msg, "id", ""),
                    "role": "ai" if msg.peer_id == self._ai_peer else "user",
                    "content": msg.content,
                }
            )
        rows.reverse()
        return rows


__all__: tuple[str, ...] = (
    "PersonaMemory",
)
"""confirm_delete Discord interaction handler (Ticket 74).

When an authorized Assistant or Main Agent user requests task deletion
without confirmation, the pre_gateway_dispatch plugin returns a
DiscordRoute with ``confirm_required=True`` and ``action: "skip"``.
The gateway adapter then sends a native Yes/No ``discord.ui.View``
confirmation prompt (design-captured in Ticket 74; the button-view
wiring lives in hermes-agent and is not implemented in this repo —
this module only handles the button click once such a view exists).

This module handles the *button click* — a Discord interaction, not
a MessageEvent — and re-invokes the contract gate with
``confirm_delete=True`` before calling the deletion operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from hermes.personas.adapters import route_discord_message, DiscordMessage
from hermes.personas.contract_gate import Decision


# ---------------------------------------------------------------------------
# Structural Protocols — mirrors hermes-agent types without importing them
# ---------------------------------------------------------------------------

class _InteractionLike(Protocol):
    """Subset of ``discord.Interaction`` fields this handler reads."""

    @property
    def user(self) -> Any: ...
    @property
    def custom_id(self) -> str: ...
    @property
    def channel_id(self) -> int: ...


class _GatewayLike(Protocol):
    """Subset of ``gateway.run.GatewayRunner`` the handler may call."""

    adapters: dict[str, Any]


# ---------------------------------------------------------------------------
# Pending confirmation state
# ---------------------------------------------------------------------------

@dataclass
class PendingDeletion:
    """State stored between the confirm prompt and the button click.

    Created when pre_gateway_dispatch requests confirmation; consumed
    by the interaction handler when the user clicks Yes/No.
    """

    persona_id: str
    author_id: str
    channel_id: str
    task_content: str
    home_channel_id: str
    allowed_users: frozenset[str]
    message_id: str = ""


# In-memory store — cleared on handler restart.
# In production, hermes-agent's session store would back this.
_pending: dict[str, PendingDeletion] = {}


def store_pending_deletion(
    interaction_id: str,
    pending: PendingDeletion,
) -> None:
    """Store a pending deletion confirmation for later retrieval."""
    _pending[interaction_id] = pending


def retrieve_pending_deletion(
    interaction_id: str,
) -> PendingDeletion | None:
    """Retrieve (and consume) a pending deletion confirmation."""
    return _pending.pop(interaction_id, None)


# ---------------------------------------------------------------------------
# Interaction handler callbacks
# ---------------------------------------------------------------------------

def handle_confirm_yes(
    pending: PendingDeletion,
    click_user_id: str,
) -> dict[str, Any]:
    """Handle a Yes click on the confirm_delete prompt.

    Returns a dict the caller uses to route the delete operation.
    """
    # Verify the clicker is the original requester.
    if click_user_id != pending.author_id:
        return {
            "action": "reject",
            "reason": f"User {click_user_id} is not the original requester {pending.author_id}",
        }

    # Re-invoke the contract gate with confirm_delete=True.
    message = DiscordMessage(
        channel_id=pending.channel_id,
        author_id=pending.author_id,
        mentions=(pending.persona_id,),
        content=pending.task_content,
        confirm_delete=True,
    )
    route = route_discord_message(
        message,
        home_channel_id=pending.home_channel_id,
        allowed_users=pending.allowed_users,
    )

    if route.decision != Decision.ALLOW:
        return {
            "action": "reject",
            "reason": route.reason or "gate refused deletion",
            "hint_persona": route.hint_persona,
        }

    return {
        "action": "delete",
        "persona_id": pending.persona_id,
        "task_content": pending.task_content,
        "author_id": pending.author_id,
    }


def handle_confirm_no(
    pending: PendingDeletion,
    click_user_id: str,
) -> dict[str, Any]:
    """Handle a No click on the confirm_delete prompt.

    Returns a no-op result; no task mutation occurs.
    """
    if click_user_id != pending.author_id:
        return {
            "action": "reject",
            "reason": f"User {click_user_id} is not the original requester",
        }
    return {
        "action": "cancel",
        "reason": "User cancelled deletion",
    }


# ---------------------------------------------------------------------------
# Interaction routing
# ---------------------------------------------------------------------------

def route_confirm_interaction(
    interaction_id: str,
    click_user_id: str,
    button: str,  # "yes" or "no"
) -> dict[str, Any]:
    """Top-level router for confirm_delete button clicks.

    Called by hermes-agent's Discord interaction handler (not
    pre_gateway_dispatch).  Returns a dict the caller uses to
    perform or skip the deletion.

    Args:
        interaction_id: The Discord interaction custom_id.
        click_user_id: The Discord user who clicked the button.
        button: "yes" or "no".

    Returns:
        {
            "action": "delete" | "cancel" | "reject",
            "reason": str,
            ...
        }
    """
    pending = retrieve_pending_deletion(interaction_id)
    if pending is None:
        return {
            "action": "reject",
            "reason": "Interaction expired or already resolved",
        }

    if button == "yes":
        return handle_confirm_yes(pending, click_user_id)
    elif button == "no":
        return handle_confirm_no(pending, click_user_id)

    return {
        "action": "reject",
        "reason": f"Unknown button value: {button}",
    }

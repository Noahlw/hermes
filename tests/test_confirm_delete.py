"""Tests for the confirm_delete interaction handler (Ticket 74)."""

from __future__ import annotations

import unittest

from hermes.hermes_agent_plugin.confirm_delete import (
    PendingDeletion,
    handle_confirm_no,
    handle_confirm_yes,
    retrieve_pending_deletion,
    route_confirm_interaction,
    store_pending_deletion,
)


class ConfirmDeleteHandlerTests(unittest.TestCase):
    """Tests for confirm_delete Yes/No interaction routing."""

    def setUp(self) -> None:
        # Clean pending store between tests.
        # _pending is module-level; drain it.
        while True:
            try:
                next(iter(_pending_keys()))
            except StopIteration:
                break
            # Drain one key.
            for k in list(_pending_keys()):
                retrieve_pending_deletion(k)

    def _make_pending(self, persona_id: str = "assistant") -> PendingDeletion:
        return PendingDeletion(
            persona_id=persona_id,
            author_id="user-1",
            channel_id="chan-1",
            task_content="delete my tasks",
            home_channel_id="chan-1",
            allowed_users=frozenset({"user-1"}),
        )

    # --- store / retrieve ---

    def test_store_and_retrieve_pending_deletion(self) -> None:
        pending = self._make_pending()
        store_pending_deletion("interaction-1", pending)
        retrieved = retrieve_pending_deletion("interaction-1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.persona_id, "assistant")
        self.assertEqual(retrieved.author_id, "user-1")

    def test_retrieve_consumes_pending_deletion(self) -> None:
        pending = self._make_pending()
        store_pending_deletion("interaction-1", pending)
        _first = retrieve_pending_deletion("interaction-1")
        second = retrieve_pending_deletion("interaction-1")
        self.assertIsNone(second)

    def test_retrieve_nonexistent_returns_none(self) -> None:
        self.assertIsNone(retrieve_pending_deletion("nonexistent"))

    # --- handle_confirm_yes ---

    def test_yes_click_by_original_user_allows_deletion(self) -> None:
        pending = self._make_pending()
        result = handle_confirm_yes(pending, "user-1")
        self.assertEqual(result["action"], "delete")
        self.assertEqual(result["persona_id"], "assistant")
        self.assertEqual(result["author_id"], "user-1")

    def test_yes_click_by_different_user_is_rejected(self) -> None:
        pending = self._make_pending()
        result = handle_confirm_yes(pending, "user-2")
        self.assertEqual(result["action"], "reject")
        self.assertIn("not the original requester", result["reason"])

    def test_yes_click_on_tutor_pending_is_refused_by_gate(self) -> None:
        """Tutor does not have manage_tasks — gate refuses even with confirm_delete=True."""
        pending = self._make_pending(persona_id="tutor")
        result = handle_confirm_yes(pending, "user-1")
        self.assertEqual(result["action"], "reject")
        # The gate result reason is surfaced — verify it's non-empty.
        self.assertTrue(result.get("reason"))

    def test_yes_click_with_wrong_channel_is_ignored_by_gate(self) -> None:
        """Gate checks channel — wrong home channel blocks deletion."""
        pending = PendingDeletion(
            persona_id="assistant",
            author_id="user-1",
            channel_id="chan-1",
            task_content="delete my tasks",
            home_channel_id="chan-2",  # different home channel
            allowed_users=frozenset({"user-1"}),
        )
        result = handle_confirm_yes(pending, "user-1")
        # confirm_delete=True but channel mismatch → gate returns a route.
        # The gate's route_discord_message will return ignored/refused.
        self.assertNotEqual(result["action"], "delete")

    def test_yes_click_with_unauthorized_user_is_ignored_by_gate(self) -> None:
        """Gate checks allowlist — unauthorized user blocked."""
        pending = PendingDeletion(
            persona_id="assistant",
            author_id="user-3",
            channel_id="chan-1",
            task_content="delete my tasks",
            home_channel_id="chan-1",
            allowed_users=frozenset({"user-1", "user-2"}),
        )
        result = handle_confirm_yes(pending, "user-3")
        self.assertNotEqual(result["action"], "delete")

    # --- handle_confirm_no ---

    def test_no_click_by_original_user_cancels(self) -> None:
        pending = self._make_pending()
        result = handle_confirm_no(pending, "user-1")
        self.assertEqual(result["action"], "cancel")
        self.assertIn("cancelled", result["reason"])

    def test_no_click_by_different_user_is_rejected(self) -> None:
        pending = self._make_pending()
        result = handle_confirm_no(pending, "user-2")
        self.assertEqual(result["action"], "reject")
        self.assertIn("not the original requester", result["reason"])

    # --- route_confirm_interaction ---

    def test_route_yes_on_valid_pending_deletes(self) -> None:
        pending = self._make_pending()
        store_pending_deletion("int-1", pending)
        result = route_confirm_interaction("int-1", "user-1", "yes")
        self.assertEqual(result["action"], "delete")

    def test_route_no_on_valid_pending_cancels(self) -> None:
        pending = self._make_pending()
        store_pending_deletion("int-1", pending)
        result = route_confirm_interaction("int-1", "user-1", "no")
        self.assertEqual(result["action"], "cancel")

    def test_route_expired_interaction_is_rejected(self) -> None:
        result = route_confirm_interaction("expired-id", "user-1", "yes")
        self.assertEqual(result["action"], "reject")
        self.assertIn("expired", result["reason"].lower())

    def test_route_already_resolved_interaction_is_rejected(self) -> None:
        pending = self._make_pending()
        store_pending_deletion("int-1", pending)
        # First click consumes it.
        route_confirm_interaction("int-1", "user-1", "yes")
        # Second click on same ID → expired.
        result = route_confirm_interaction("int-1", "user-1", "yes")
        self.assertEqual(result["action"], "reject")

    def test_route_unknown_button_is_rejected(self) -> None:
        pending = self._make_pending()
        store_pending_deletion("int-1", pending)
        result = route_confirm_interaction("int-1", "user-1", "maybe")
        self.assertEqual(result["action"], "reject")

    def test_route_different_user_yes_is_rejected(self) -> None:
        pending = self._make_pending()
        store_pending_deletion("int-1", pending)
        result = route_confirm_interaction("int-1", "user-2", "yes")
        self.assertEqual(result["action"], "reject")

    # --- Acceptance tests from #74 ---

    def test_yes_triggers_deletion_only_after_gate_allows(self) -> None:
        """Acceptance: Yes click invokes gate with confirm_delete=True."""
        pending = self._make_pending(persona_id="assistant")
        store_pending_deletion("int-accept-1", pending)
        result = route_confirm_interaction("int-accept-1", "user-1", "yes")
        self.assertEqual(result["action"], "delete")
        # The pending is consumed.
        self.assertIsNone(retrieve_pending_deletion("int-accept-1"))

    def test_no_leaves_task_intact(self) -> None:
        """Acceptance: No click → no deletion, no mutation."""
        pending = self._make_pending()
        store_pending_deletion("int-accept-2", pending)
        result = route_confirm_interaction("int-accept-2", "user-1", "no")
        self.assertEqual(result["action"], "cancel")

    def test_expired_interaction_does_not_delete(self) -> None:
        """Acceptance: expired interactions are safe no-ops."""
        result = route_confirm_interaction("stale-id", "user-1", "yes")
        self.assertEqual(result["action"], "reject")

    def test_duplicate_click_does_not_delete_twice(self) -> None:
        """Acceptance: already-resolved interactions do not delete twice."""
        pending = self._make_pending()
        store_pending_deletion("int-dup", pending)
        first = route_confirm_interaction("int-dup", "user-1", "yes")
        self.assertEqual(first["action"], "delete")
        second = route_confirm_interaction("int-dup", "user-1", "yes")
        self.assertEqual(second["action"], "reject")

    def test_tutor_cannot_delete_even_with_confirm(self) -> None:
        """Acceptance: Tutor cannot reach task deletion even with confirm button."""
        pending = self._make_pending(persona_id="tutor")
        store_pending_deletion("int-tutor", pending)
        result = route_confirm_interaction("int-tutor", "user-1", "yes")
        self.assertEqual(result["action"], "reject")

    def test_different_user_cannot_click_original_users_yes(self) -> None:
        """Acceptance: a different user clicking the original user's Yes is rejected."""
        pending = self._make_pending()
        store_pending_deletion("int-other", pending)
        result = route_confirm_interaction("int-other", "user-2", "yes")
        self.assertEqual(result["action"], "reject")


def _pending_keys() -> set[str]:
    """Access the module-level _pending dict for test cleanup."""
    from hermes.hermes_agent_plugin import confirm_delete as mod
    return set(mod._pending.keys())


if __name__ == "__main__":
    unittest.main()

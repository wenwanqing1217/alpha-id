"""
Core interfaces for dependency inversion.

These protocols define the contracts that core modules depend on,
allowing alpha_id/ to provide concrete implementations without
creating circular dependencies.
"""

from typing import Any, Dict, List, Optional


class IdentityBackend:
    """User identity and profile operations."""

    def get_user_profile(self, alpha_id: str) -> Optional[Dict[str, Any]]: ...  # pragma: no cover


class SocialBackend:
    """Social graph and messaging operations."""

    def get_friends(self, alpha_id: str) -> List[Dict[str, Any]]: ...  # pragma: no cover

    def get_messages(self, alpha_id: str, unread_only: bool = False) -> List[Dict[str, Any]]: ...  # pragma: no cover

    def send_message(
        self, from_alpha_id: str, to_alpha_id: str, content: str
    ) -> Dict[str, Any]: ...  # pragma: no cover

    def send_friend_request(
        self, from_alpha_id: str, to_alpha_id: str, message: str = ""
    ) -> Dict[str, Any]: ...  # pragma: no cover


class PoEStore:
    """Proof of Execution storage."""

    def save(self, execution: Dict[str, Any]) -> None: ...  # pragma: no cover

    def get(self, execution_id: str) -> Optional[Dict[str, Any]]: ...  # pragma: no cover


class SkillAttributionTracker:
    """Track skill usage attribution."""

    def record(self, skill_name: str, alpha_id: str, **kwargs: Any) -> None: ...  # pragma: no cover


class SkillRuntime:
    """Execute installed skills."""

    def execute(self, name: str, params: Dict[str, Any], executor_did: str) -> str: ...  # pragma: no cover


class AgentContainer:
    """Container protocol for Agent dependencies."""

    @property
    def identity(self) -> "IdentityBackend": ...  # pragma: no cover

    @property
    def social(self) -> "SocialBackend": ...  # pragma: no cover

    @property
    def risk(self) -> Any: ...  # pragma: no cover

    @property
    def memory(self) -> Any: ...  # pragma: no cover

    @property
    def actions(self) -> Any: ...  # pragma: no cover

    @property
    def skill_tracker(self) -> "SkillAttributionTracker": ...  # pragma: no cover

    @property
    def skill_runtime(self) -> "SkillRuntime": ...  # pragma: no cover

    @property
    def poe_store(self) -> "PoEStore": ...  # pragma: no cover

"""Abstract interface for the daemon's assistant engine."""

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class PromptContext:
    """Structured context passed to the engine for prompt execution."""
    session_id: str
    prompt: str
    workspace_root: Path
    project_path: str
    active_files: List[str] = field(default_factory=list)
    mode: str = "code"


class AssistantEngine(abc.ABC):
    """Abstract interface hiding Aider execution details from the daemon."""

    @abc.abstractmethod
    async def submit_prompt(self, context: Union[PromptContext, str], prompt: Optional[str] = None) -> None:
        """Submit a prompt for processing."""
        pass

    @abc.abstractmethod
    async def cancel(self, session_id: str) -> None:
        """Cancel the currently executing prompt for the session."""
        pass

    @abc.abstractmethod
    async def get_status(self, session_id: str) -> Dict[str, Any]:
        """Get the current status of the engine."""
        pass

    @abc.abstractmethod
    async def reset(self, session_id: str) -> None:
        """Reset the engine state (clear context)."""
        pass


class StubAssistantEngine(AssistantEngine):
    """Stub implementation for testing and development."""

    async def submit_prompt(self, context: Union[PromptContext, str], prompt: Optional[str] = None) -> None:
        pass

    async def cancel(self, session_id: str) -> None:
        pass

    async def get_status(self, session_id: str) -> Dict[str, Any]:
        return {"state": "idle"}

    async def reset(self, session_id: str) -> None:
        pass


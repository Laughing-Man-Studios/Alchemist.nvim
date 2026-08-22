"""Abstract interface for the daemon's assistant engine."""

import abc
from typing import Any, Dict

class AssistantEngine(abc.ABC):
    """Abstract interface hiding Aider execution details from the daemon."""

    @abc.abstractmethod
    async def submit_prompt(self, session_id: str, prompt: str) -> None:
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
    """Stub implementation for Phase 2."""
    
    async def submit_prompt(self, session_id: str, prompt: str) -> None:
        pass
        
    async def cancel(self, session_id: str) -> None:
        pass
        
    async def get_status(self, session_id: str) -> Dict[str, Any]:
        return {"state": "idle"}
        
    async def reset(self, session_id: str) -> None:
        pass

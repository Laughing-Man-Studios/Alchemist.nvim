"""Active job tracking to enforce V1 global serialization rules."""

from typing import Dict, Any, Optional
import time

from alchemist.errors import AgentBusyError

class ActiveJobTracker:
    """Enforces the one-active-agent-job-globally constraint."""
    
    def __init__(self):
        self._active_job: Optional[Dict[str, Any]] = None

    def start_job(self, session_id: str, project_id: str, task_description: str) -> None:
        """Register a new active job. Raises AgentBusyError if one is already running."""
        if self._active_job is not None:
            summary = self._active_job.get("task_description", "Unknown task")
            raise AgentBusyError(
                f"Cannot start job. Another job is currently running in session "
                f"{self._active_job['session_id']} (Project: {self._active_job['project_id']}). "
                f"Summary: {summary}",
                details={"active_job": self._active_job}
            )
            
        self._active_job = {
            "session_id": session_id,
            "project_id": project_id,
            "task_description": task_description,
            "started_at": time.time()
        }

    def clear_job(self, session_id: str) -> None:
        """Clear the active job if it matches the session_id."""
        if self._active_job and self._active_job["session_id"] == session_id:
            self._active_job = None

    def force_clear(self) -> None:
        """Force clear any active job (e.g. during reset)."""
        self._active_job = None
        
    def get_current_job(self) -> Optional[Dict[str, Any]]:
        """Return the current active job details."""
        return dict(self._active_job) if self._active_job else None

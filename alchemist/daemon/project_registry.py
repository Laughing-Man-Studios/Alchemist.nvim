"""Project registry and session management."""

import uuid
from typing import Dict, Optional

class ProjectState:
    def __init__(self, project_id: str, path: str):
        self.project_id = project_id
        self.path = path
        self.shadow_workspace_root: Optional[str] = None
        self.active_session_id: Optional[str] = None
        
class ProjectRegistry:
    """Tracks project state, active sessions, and client mapping."""
    def __init__(self):
        self._projects: Dict[str, ProjectState] = {}
        # Maps client_id -> project_id
        self._client_to_project: Dict[str, str] = {}
        
    def register_project(self, project_id: str, path: str) -> ProjectState:
        if project_id not in self._projects:
            self._projects[project_id] = ProjectState(project_id, path)
        return self._projects[project_id]
        
    def get_project(self, project_id: str) -> Optional[ProjectState]:
        return self._projects.get(project_id)
        
    def link_client_to_project(self, client_id: str, project_id: str) -> None:
        self._client_to_project[client_id] = project_id
        
    def get_project_for_client(self, client_id: str) -> Optional[str]:
        return self._client_to_project.get(client_id)

class SessionManager:
    """Generates and tracks session IDs."""
    @staticmethod
    def generate_session_id() -> str:
        return str(uuid.uuid4())

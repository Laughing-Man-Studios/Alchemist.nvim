"""Shadow workspace engine for isolated Aider execution."""

from alchemist.workspace.diff import DiffGenerator
from alchemist.workspace.ignore import collect_files_for_shadow, is_binary_file
from alchemist.workspace.lifecycle import AcceptanceFlow, RejectionFlow
from alchemist.workspace.manager import ShadowManager, ShadowWorkspace
from alchemist.workspace.orchestrator import PromptOrchestrator
from alchemist.workspace.sync import PreFlightSync

__all__ = [
    "AcceptanceFlow",
    "DiffGenerator",
    "PreFlightSync",
    "PromptOrchestrator",
    "RejectionFlow",
    "ShadowManager",
    "ShadowWorkspace",
    "collect_files_for_shadow",
    "is_binary_file",
]

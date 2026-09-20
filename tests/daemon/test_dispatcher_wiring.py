"""Tests for daemon method registry wiring and stubs."""

from unittest.mock import MagicMock
import pytest

from alchemist.daemon.active_job import ActiveJobTracker
from alchemist.daemon.broadcaster import Broadcaster
from alchemist.daemon.dispatcher import build_default_registry
from alchemist.engine.interface import StubAssistantEngine
from alchemist.workspace.manager import ShadowManager
from alchemist.workspace.orchestrator import PromptOrchestrator


def test_agent_methods_wired_with_orchestrator():
    """All agent methods should resolve to real handlers when orchestrator is present."""
    orchestrator = PromptOrchestrator(
        shadow_manager=ShadowManager(),
        engine=StubAssistantEngine(),
        job_tracker=ActiveJobTracker(),
        broadcaster=MagicMock(spec=Broadcaster),
    )
    registry = build_default_registry(
        lifecycle=MagicMock(),
        socket_path="/tmp/test.sock",
        orchestrator=orchestrator,
        vault=MagicMock(),
    )
    agent_methods = [
        "agent/submit_prompt", "agent/cancel", "agent/status", "agent/list_sessions",
        "agent/reset", "agent/clear", "agent/add_file", "agent/drop_file",
        "agent/list_files", "agent/read_only", "agent/repo_map",
        "agent/run", "agent/test", "agent/lint",
        "agent/accept_diff", "agent/reject_diff",
    ]
    for method in agent_methods:
        handler = registry.get(method)
        assert handler is not None, f"{method} should be registered"
        assert handler.__name__ != "handle_not_implemented", f"{method} should not be a stub"

    config_methods = [
        "config/set_key", "config/list_providers", "config/list_keys", "config/delete_key",
    ]
    for method in config_methods:
        handler = registry.get(method)
        assert handler is not None, f"{method} should be registered"
        assert handler.__name__ != "handle_not_implemented", f"{method} should not be a stub"


def test_agent_methods_stubbed_without_orchestrator():
    """All agent methods should be stubs when no orchestrator is provided."""
    registry = build_default_registry(
        lifecycle=MagicMock(),
        socket_path="/tmp/test.sock",
        orchestrator=None,
        vault=MagicMock(),
    )
    for method in ["agent/cancel", "agent/status", "agent/reset", "agent/run"]:
        handler = registry.get(method)
        assert handler is not None
        assert handler.__name__ == "handle_not_implemented"

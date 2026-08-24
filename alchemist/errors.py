"""Centralized exception hierarchy and error normalization for the daemon."""

from typing import Dict, Any

class AlchemistError(Exception):
    """Base exception for all daemon-specific errors."""
    code: str = "INTERNAL_ERROR"
    retryable: bool = False
    default_hint: str = "An unexpected error occurred."
    
    def __init__(self, message: str, hint: str | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        self.hint = hint or self.default_hint
        self.details = details

    def to_dict(self) -> Dict[str, Any]:
        """Convert to the data payload format for JSON-RPC error envelopes."""
        res = {
            "code": self.code,
            "retryable": self.retryable,
            "hint": self.hint,
        }
        if self.details is not None:
            res["details"] = self.details
        return res

class NoKeysConfiguredError(AlchemistError):
    code = "NO_KEYS_CONFIGURED"
    retryable = False
    default_hint = "Use :Alchemist config set_key to add an API key."

class AllKeysExhaustedError(AlchemistError):
    code = "ALL_KEYS_EXHAUSTED"
    retryable = True
    default_hint = "All configured API keys have exceeded their quotas or returned 429."

class DaemonVersionMismatchError(AlchemistError):
    code = "DAEMON_VERSION_MISMATCH"
    retryable = False
    default_hint = "Please run setup again to update the daemon to the expected protocol version."

class FrameTooLargeError(AlchemistError):
    code = "FRAME_TOO_LARGE"
    retryable = False
    default_hint = "The sent payload exceeded the 16 MiB size limit."

class AgentBusyError(AlchemistError):
    code = "AGENT_BUSY"
    retryable = True
    default_hint = "Another job is currently running. Please wait or cancel it."

class NotImplementedErrorResponse(AlchemistError):
    code = "NOT_IMPLEMENTED"
    retryable = False
    default_hint = "This feature is not yet implemented in the daemon."

class ShadowSyncFailedError(AlchemistError):
    code = "SHADOW_SYNC_FAILED"
    retryable = False
    default_hint = "Shadow workspace synchronization failed. Try restarting the daemon."

class PatchApplyFailedError(AlchemistError):
    code = "PATCH_APPLY_FAILED"
    retryable = False
    default_hint = (
        "Patch application failed. Buffers were restored from snapshots. "
        "Reopen the diff or retry the prompt."
    )

class ShadowWorkspaceNotInitializedError(AlchemistError):
    code = "SHADOW_SYNC_FAILED"
    retryable = True
    default_hint = "No shadow workspace is active. Submit a prompt to initialize one."


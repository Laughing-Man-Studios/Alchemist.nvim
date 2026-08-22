"""Constants and pinned versions for the daemon."""

import os
import sys

# Protocol and System Versions
DAEMON_VERSION = "0.1.0"
PROTOCOL_VERSION = "1.0.0"
AIDER_VERSION = "0.72.0"  # or dynamically retrieved, but pinned per Phase 2 requirements

# Defaults
DEFAULT_MODEL = "gemini/gemini-2.5-flash"

# IO Constraints
MAX_FRAME_SIZE = 16 * 1024 * 1024  # 16 MiB

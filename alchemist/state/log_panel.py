"""In-memory ring buffer for the :AlchemistLogs command."""

from collections import deque
import time
from typing import Dict, Any, List

class LogPanelBuffer:
    """Stores a bounded history of operational errors and hints."""
    
    def __init__(self, max_size: int = 100):
        self._buffer: deque[Dict[str, Any]] = deque(maxlen=max_size)

    def append(self, level: str, code: str, message: str, hint: str) -> None:
        """Add a log entry to the buffer."""
        self._buffer.append({
            "timestamp": time.time(),
            "level": level,
            "code": code,
            "message": message,
            "hint": hint
        })

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve the most recent logs, up to the limit."""
        # Convert deque to list and slice the end
        logs = list(self._buffer)
        if len(logs) > limit:
            return logs[-limit:]
        return logs

    def clear(self) -> None:
        """Clear the log buffer."""
        self._buffer.clear()

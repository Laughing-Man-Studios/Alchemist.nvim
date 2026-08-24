"""Atomic file locking utilities for the daemon."""

import fcntl
import os
import sys
from pathlib import Path
from typing import Optional
from .paths import get_lockfile_path, ensure_runtime_dir

class LockAcquisitionError(Exception):
    """Raised when the lockfile cannot be acquired."""
    pass

class DaemonLock:
    """Manages the single-instance OS-level file lock."""
    def __init__(self):
        self.lock_path: Path = get_lockfile_path()
        self._fd: Optional[int] = None

    def acquire(self) -> None:
        """Acquire the lock, raising LockAcquisitionError if already locked."""
        ensure_runtime_dir()
        
        try:
            # Open the file, creating it if necessary
            self._fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            # Try to acquire an exclusive, non-blocking lock
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError) as e:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            raise LockAcquisitionError(f"Another daemon is already running (failed to acquire {self.lock_path}): {e}")

    def release(self) -> None:
        """Release the lock and clean up the file."""
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
                if self.lock_path.exists():
                    self.lock_path.unlink()
            except OSError:
                pass
            finally:
                self._fd = None

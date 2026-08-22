"""Centralized path resolution and normalization utilities."""

import os
from pathlib import Path

def _get_runtime_dir() -> Path:
    """Resolve the base runtime directory ($XDG_RUNTIME_DIR or /tmp fallback)."""
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        return Path(xdg)
    
    # Fallback to /tmp with user scoping
    user = os.environ.get("USER", "unknown")
    return Path(f"/tmp/alchemist_{user}")

def get_socket_path() -> Path:
    """Resolve the daemon Unix socket path."""
    return _get_runtime_dir() / "alchemist.sock"

def get_lockfile_path() -> Path:
    """Resolve the daemon lockfile path."""
    return _get_runtime_dir() / "alchemist.lock"

def get_config_dir() -> Path:
    """Resolve the Alchemist configuration directory (~/.config/alchemist)."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "alchemist"
    return Path.home() / ".config" / "alchemist"

def get_vault_path() -> Path:
    """Resolve the encrypted vault path."""
    return get_config_dir() / "vault.enc"

def get_ledger_path() -> Path:
    """Resolve the SQLite ledger path."""
    return get_config_dir() / "telemetry.db"

def ensure_config_dir() -> None:
    """Ensure the configuration directory exists with safe permissions."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(config_dir, 0o700)

def ensure_runtime_dir() -> None:
    """Ensure the runtime directory exists with safe permissions."""
    runtime_dir = _get_runtime_dir()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(runtime_dir, 0o700)

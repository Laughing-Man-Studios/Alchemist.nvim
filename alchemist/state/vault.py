"""Local encrypted vault management for API keys."""

import json
import os
import stat
from typing import Dict, List, Optional, Any
from pydantic import SecretStr

from alchemist.daemon.paths import get_vault_path, ensure_config_dir

class LocalVault:
    """Manages the encrypted JSON vault (encryption stubbed for Phase 2)."""
    
    def __init__(self):
        self.vault_path = get_vault_path()

    def _ensure_vault_exists(self) -> None:
        """Create an empty vault if it doesn't exist, enforcing 0600."""
        ensure_config_dir()
        if not self.vault_path.exists():
            # Create securely
            fd = os.open(self.vault_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(fd, 'w') as f:
                json.dump({"keys": {}}, f)

    def _read_vault(self) -> Dict[str, Any]:
        """Read and parse the vault payload."""
        self._ensure_vault_exists()
        with open(self.vault_path, 'r') as f:
            try:
                data = json.load(f)
                return data
            except json.JSONDecodeError:
                return {"keys": {}}

    def _write_vault(self, data: Dict[str, Any]) -> None:
        """Write the vault payload, preserving 0600."""
        self._ensure_vault_exists()
        
        # Write to temporary file, then atomic rename
        tmp_path = self.vault_path.with_suffix(".tmp")
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
            
        os.rename(tmp_path, self.vault_path)

    def set_key(self, provider: str, api_key: SecretStr) -> str:
        """Set a key and return a masked confirmation."""
        data = self._read_vault()
        if "keys" not in data:
            data["keys"] = {}
        
        if provider not in data["keys"]:
            data["keys"][provider] = []
            
        # Append the new key. (Phase 2 stub: storing plain text, Phase 5 adds real crypto)
        data["keys"][provider].append(api_key.get_secret_value())
        self._write_vault(data)
        
        # Masked confirmation
        val = api_key.get_secret_value()
        if len(val) > 8:
            masked = f"{val[:4]}...{val[-4:]}"
        else:
            masked = "***"
            
        return masked

    def list_providers(self) -> List[str]:
        """List supported providers."""
        # For V1, hardcode supported providers
        return ["gemini", "deepseek", "qwen", "openai", "anthropic"]

    def list_keys(self) -> Dict[str, List[int]]:
        """List provider names and key indices (no raw keys)."""
        data = self._read_vault()
        keys_dict = data.get("keys", {})
        result = {}
        for provider, keys in keys_dict.items():
            result[provider] = list(range(len(keys)))
        return result

    def delete_key(self, provider: str, index: int) -> bool:
        """Delete a key by index."""
        data = self._read_vault()
        if "keys" not in data or provider not in data["keys"]:
            return False
            
        keys = data["keys"][provider]
        if 0 <= index < len(keys):
            keys.pop(index)
            if not keys:
                del data["keys"][provider]
            self._write_vault(data)
            return True
        return False
        
    def get_key(self, provider: str, index: int) -> Optional[SecretStr]:
        """Internal method to get a key for the LLM client."""
        data = self._read_vault()
        keys = data.get("keys", {}).get(provider, [])
        if 0 <= index < len(keys):
            return SecretStr(keys[index])
        return None

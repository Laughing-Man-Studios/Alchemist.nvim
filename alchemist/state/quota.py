"""In-memory quota tracking."""

import time
from typing import Dict, Tuple, Any

class QuotaState:
    ACTIVE = "active"
    COOLDOWN = "cooldowned"
    EXHAUSTED = "exhausted"

class QuotaTracker:
    """Tracks high-frequency quota metrics in memory."""
    def __init__(self):
        # Keyed by (provider, key_index)
        self._quotas: Dict[Tuple[str, int], Dict[str, Any]] = {}

    def _init_quota(self, provider: str, key_index: int) -> None:
        key = (provider, key_index)
        if key not in self._quotas:
            self._quotas[key] = {
                "rpm": 0,
                "tpm": 0,
                "rpd": 0,
                "tpd": 0,
                "cooldown_until": 0.0,
                "last_request_ts": 0.0,
                "state": QuotaState.ACTIVE
            }

    def get_quota(self, provider: str, key_index: int) -> Dict[str, Any]:
        """Get the quota dict for a specific provider/key pair."""
        self._init_quota(provider, key_index)
        return self._quotas[(provider, key_index)]

    def update_usage(self, provider: str, key_index: int, tokens: int) -> None:
        """Update metrics for a successful request."""
        self._init_quota(provider, key_index)
        q = self._quotas[(provider, key_index)]
        
        q["rpm"] += 1
        q["rpd"] += 1
        q["tpm"] += tokens
        q["tpd"] += tokens
        q["last_request_ts"] = time.time()
        
    def set_cooldown(self, provider: str, key_index: int, seconds: float) -> None:
        """Place a key into cooldown (e.g. on 429)."""
        self._init_quota(provider, key_index)
        q = self._quotas[(provider, key_index)]
        q["state"] = QuotaState.COOLDOWN
        q["cooldown_until"] = time.time() + seconds
        
    def set_exhausted(self, provider: str, key_index: int) -> None:
        """Mark a key as completely exhausted."""
        self._init_quota(provider, key_index)
        q = self._quotas[(provider, key_index)]
        q["state"] = QuotaState.EXHAUSTED

"""LiteLLM interception layer to track token usage, inject keys, and handle rotation."""

import logging
from typing import Any, Dict, List, Optional
import litellm

logger = logging.getLogger(__name__)

class LiteLLMInterceptor:
    """Intercepts litellm calls for metrics and error handling."""
    
    def __init__(self, fake_provider: Optional[Any] = None):
        # Allow injecting a fake provider for tests
        self._fake_provider = fake_provider
        
        # Stub hook slots for Phase 5 integration
        self.pre_request_hooks = []
        self.post_request_hooks = []
        self.error_hooks = []

    def _get_api_key(self, provider: str, model: str) -> Optional[str]:
        """Stub: retrieve API key from vault."""
        return None

    async def acompletion(self, model: str, messages: List[Dict[str, str]], **kwargs: Any) -> Any:
        """Wrap litellm.acompletion with interception logic."""
        provider = model.split("/")[0] if "/" in model else "unknown"
        
        # Pre-request hooks (e.g. check quota, set api_key)
        for hook in self.pre_request_hooks:
            await hook(provider, model, messages, kwargs)

        try:
            if self._fake_provider:
                response = await self._fake_provider.acompletion(model, messages, **kwargs)
            else:
                # Phase 2 stub: just passthrough to real litellm
                api_key = self._get_api_key(provider, model)
                if api_key:
                    kwargs["api_key"] = api_key
                response = await litellm.acompletion(model, messages, **kwargs)
                
            # Post-request hooks (e.g. log usage)
            for hook in self.post_request_hooks:
                await hook(provider, model, response)
                
            return response
            
        except Exception as e:
            # Error hooks (e.g. handle 429 rotation)
            for hook in self.error_hooks:
                await hook(provider, model, e)
            raise

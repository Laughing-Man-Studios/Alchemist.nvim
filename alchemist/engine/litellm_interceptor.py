"""Synchronous, request-scoped LiteLLM interception for Aider."""

import logging
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional
import litellm
from pydantic import SecretStr

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

    @contextmanager
    def scoped_completion(self, api_key: SecretStr) -> Iterator[None]:
        """Patch only the blocking completion Aider uses, then always restore it."""
        original = litellm.completion

        def completion(*args: Any, **kwargs: Any) -> Any:
            kwargs["api_key"] = api_key.get_secret_value()
            model = kwargs.get("model") or (args[0] if args else "unknown")
            provider = str(model).split("/", 1)[0]
            for hook in self.pre_request_hooks:
                hook(provider, model, kwargs)
            try:
                response = (self._fake_provider.completion(*args, **kwargs)
                            if self._fake_provider else original(*args, **kwargs))
                for hook in self.post_request_hooks:
                    hook(provider, model, response)
                return response
            except Exception as exc:
                for hook in self.error_hooks:
                    hook(provider, model, exc)
                raise

        litellm.completion = completion
        try:
            yield
        finally:
            litellm.completion = original

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

"""Routing matrix for model selection (stub)."""

from typing import Dict, Any

class RoutingPolicy:
    """Matrix for determining the best model to use based on constraints."""
    
    @staticmethod
    def get_fallback_chain() -> list[str]:
        """Return the hardcoded fallback logic for Phase 2."""
        return [
            "gemini/gemini-2.5-flash",
            "deepseek/deepseek-chat",
            "qwen/qwen-72b-chat",
        ]
        
    @staticmethod
    def route_request(task_type: str, available_providers: list[str]) -> str:
        """Determine the model to route to."""
        # Stub logic: just pick the first fallback available
        chain = RoutingPolicy.get_fallback_chain()
        for model in chain:
            provider = model.split("/")[0]
            if provider in available_providers:
                return model
        # Default fallback
        return chain[0]

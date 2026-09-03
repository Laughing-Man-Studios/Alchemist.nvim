"""Configured-provider-only model routing."""

from typing import Dict, Any

class RoutingPolicy:
    """Matrix for determining the best model to use based on constraints."""
    
    CHAINS = {
        "code": ["deepseek/deepseek-chat", "qwen/qwen-72b-chat"],
        "architect": ["qwen/qwen-72b-chat", "gemini/gemini-2.5-flash"],
        # Cheap-first ordering; only configured providers may be selected.
        "ask": ["deepseek/deepseek-chat", "qwen/qwen-72b-chat", "gemini/gemini-2.5-flash"],
    }

    @classmethod
    def get_fallback_chain(cls, task_type: str = "code") -> list[str]:
        return list(cls.CHAINS.get(task_type, cls.CHAINS["code"]))
        
    @staticmethod
    def route_request(task_type: str, available_providers: list[str]) -> str:
        """Determine the model to route to."""
        chain = RoutingPolicy.get_fallback_chain(task_type)
        for model in chain:
            provider = model.split("/")[0]
            if provider in available_providers:
                return model
        raise ValueError("No configured provider supports this prompt mode")

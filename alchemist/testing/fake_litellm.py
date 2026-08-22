"""Fake LiteLLM provider for deterministic testing."""

from typing import Any, AsyncGenerator, Dict, List, Optional
import time

class FakeLiteLLMProvider:
    """Simulates litellm.acompletion and litellm.completion."""
    
    def __init__(self):
        self.scenarios: Dict[str, Any] = {}
        self.call_history: List[Dict[str, Any]] = []
        
    def set_scenario(self, prompt_keyword: str, response: Any, error: Optional[Exception] = None) -> None:
        """Configure a mock response or error for a specific keyword in the prompt."""
        self.scenarios[prompt_keyword] = {
            "response": response,
            "error": error
        }

    async def acompletion(self, model: str, messages: List[Dict[str, str]], stream: bool = False, **kwargs: Any) -> Any:
        """Simulate an async completion call."""
        # Record the call
        self.call_history.append({
            "model": model,
            "messages": messages,
            "stream": stream,
            "kwargs": kwargs,
            "timestamp": time.time()
        })
        
        # Look for matching scenario
        prompt_text = " ".join([m.get("content", "") for m in messages])
        
        for keyword, scenario in self.scenarios.items():
            if keyword in prompt_text:
                if scenario["error"]:
                    raise scenario["error"]
                if stream:
                    return self._stream_generator(scenario["response"])
                return self._build_response(scenario["response"])
                
        # Default response
        default_resp = "This is a fake response."
        if stream:
            return self._stream_generator(default_resp)
        return self._build_response(default_resp)

    async def _stream_generator(self, text: str) -> AsyncGenerator[Any, None]:
        """Simulate a streaming response."""
        words = text.split(" ")
        for i, word in enumerate(words):
            chunk = type("Chunk", (), {})()
            chunk.choices = [type("Choice", (), {})()]
            chunk.choices[0].delta = type("Delta", (), {"content": word + (" " if i < len(words) - 1 else "")})()
            yield chunk

    def _build_response(self, text: str) -> Any:
        """Build a mock LiteLLM response object."""
        resp = type("Response", (), {})()
        resp.choices = [type("Choice", (), {})()]
        resp.choices[0].message = type("Message", (), {"content": text})()
        
        # Usage metadata mock
        resp.usage = type("Usage", (), {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        })()
        return resp

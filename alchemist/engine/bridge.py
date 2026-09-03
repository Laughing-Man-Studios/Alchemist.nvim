"""Thread-isolated bridge for Aider engine execution."""

import asyncio
import concurrent.futures
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

class ThreadIsolatedBridge:
    """Bridges blocking Aider tasks to the main asyncio event loop."""
    
    def __init__(self, main_loop: asyncio.AbstractEventLoop):
        self._loop = main_loop
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._confirmation_callbacks: Dict[str, asyncio.Future] = {}

    def run_in_thread(self, func: Callable, *args: Any, **kwargs: Any) -> asyncio.Future:
        """Run a blocking function in the background thread."""
        return self._loop.run_in_executor(self._thread_pool, lambda: func(*args, **kwargs))

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """The daemon loop used to marshal worker-thread notifications."""
        return self._loop

    def request_confirmation_sync(
        self, 
        session_id: str, 
        prompt_type: str, 
        prompt_text: str,
        timeout: float = 60.0,
        default_fallback: Any = False
    ) -> Any:
        """
        Called from the background thread to ask the client for confirmation.
        Blocks the background thread until the client responds or times out.
        """
        future = concurrent.futures.Future()
        
        async def _ask_client():
            try:
                # Stub: Normally this would use Broadcaster to send to client
                # and store an asyncio.Future waiting for the response RPC.
                # For Phase 2, we simulate a fast fallback if not wired up.
                logger.info(f"Requesting confirmation from client: {prompt_text}")
                
                # Simulate timeout/default for Phase 2 test
                await asyncio.sleep(0.1)
                return default_fallback
            except Exception as e:
                logger.error(f"Error during confirmation round-trip: {e}")
                return default_fallback
                
        # Fire coroutine in main loop
        coro_future = asyncio.run_coroutine_threadsafe(_ask_client(), self._loop)
        
        try:
            return coro_future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.warning(f"Confirmation request timed out after {timeout}s, using default: {default_fallback}")
            coro_future.cancel()
            return default_fallback

    def shutdown(self) -> None:
        """Shutdown the background thread pool."""
        self._thread_pool.shutdown(wait=False, cancel_futures=True)

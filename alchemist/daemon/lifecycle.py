"""Lifecycle management, signal handling, and shutdown coordination."""

import asyncio
import logging
import signal
import sys
from typing import Callable, Coroutine, Any, List

logger = logging.getLogger(__name__)

class LifecycleManager:
    """Manages daemon shutdown sequence, reference counting, and OS signals."""
    def __init__(self, grace_period_seconds: float = 15.0):
        self._active_clients: int = 0
        self._grace_period_seconds = grace_period_seconds
        self._shutdown_task: asyncio.Task | None = None
        self._cleanup_callbacks: List[Callable[[], Coroutine[Any, Any, None]]] = []
        self._shutdown_event = asyncio.Event()

    def register_cleanup_callback(self, coro: Callable[[], Coroutine[Any, Any, None]]) -> None:
        """Register an async coroutine to run during graceful shutdown."""
        self._cleanup_callbacks.append(coro)

    def client_connected(self) -> None:
        """Increment client count and cancel any pending shutdown."""
        self._active_clients += 1
        logger.debug(f"Client connected. Active clients: {self._active_clients}")
        if self._shutdown_task and not self._shutdown_task.done():
            logger.info("Cancelling grace period shutdown due to new client connection.")
            self._shutdown_task.cancel()
            self._shutdown_task = None

    def client_disconnected(self) -> None:
        """Decrement client count and start grace period if it reaches zero."""
        self._active_clients = max(0, self._active_clients - 1)
        logger.debug(f"Client disconnected. Active clients: {self._active_clients}")
        if self._active_clients == 0 and not self._shutdown_task and not self._shutdown_event.is_set():
            logger.info(f"Zero active clients. Initiating {self._grace_period_seconds}s grace period.")
            self._shutdown_task = asyncio.create_task(self._grace_period_waiter())

    @property
    def active_clients(self) -> int:
        return self._active_clients

    async def _grace_period_waiter(self) -> None:
        """Wait for the grace period, then trigger shutdown."""
        try:
            await asyncio.sleep(self._grace_period_seconds)
            logger.info("Grace period expired with zero clients. Shutting down.")
            await self.trigger_shutdown()
        except asyncio.CancelledError:
            pass # Shutdown was cancelled by a new connection

    async def trigger_shutdown(self) -> None:
        """Execute all cleanup callbacks and set the shutdown event to exit the main loop."""
        if self._shutdown_event.is_set():
            return
        
        logger.info("Executing shutdown sequence...")
        self._shutdown_event.set()
        
        # Run all registered cleanups concurrently if order isn't strict, or sequentially.
        # Sequential is usually safer for databases vs sockets.
        for cb in self._cleanup_callbacks:
            try:
                await cb()
            except Exception as e:
                logger.error(f"Error during cleanup callback: {e}", exc_info=True)

    def wait_for_shutdown(self) -> Coroutine[Any, Any, None]:
        """Coroutine that returns when a shutdown has been triggered."""
        return self._shutdown_event.wait()

    def setup_signal_handlers(self) -> None:
        """Install handlers for SIGTERM, SIGINT, and SIGHUP."""
        loop = asyncio.get_running_loop()

        def _handle_terminate_signal(sig: signal.Signals) -> None:
            logger.info(f"Received signal {sig.name}, bypassing grace period and shutting down immediately.")
            if self._shutdown_task and not self._shutdown_task.done():
                self._shutdown_task.cancel()
            asyncio.create_task(self.trigger_shutdown())

        def _handle_sighup() -> None:
            logger.info("Received SIGHUP, ignoring.")

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _handle_terminate_signal, sig)
        
        loop.add_signal_handler(signal.SIGHUP, _handle_sighup)

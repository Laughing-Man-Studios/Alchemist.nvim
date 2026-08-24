# /// script
# requires-python = "==3.12.*"
# dependencies = [
#     "aider-chat>=0.72.0",
#     "litellm>=1.0.0",
#     "pydantic>=2.0",
#     "aiosqlite>=0.20.0",
#     "cryptography>=44.0.0",
# ]
# ///

"""Main entry point for the Alchemist daemon."""

import asyncio
import logging
import sys

from alchemist.daemon.active_job import ActiveJobTracker
from alchemist.daemon.broadcaster import Broadcaster
from alchemist.daemon.dispatcher import RpcDispatcher, build_default_registry
from alchemist.daemon.lifecycle import LifecycleManager
from alchemist.daemon.lock import DaemonLock, LockAcquisitionError
from alchemist.daemon.paths import ensure_config_dir, ensure_runtime_dir, get_socket_path
from alchemist.daemon.server import IpcServer
from alchemist.engine.interface import StubAssistantEngine
from alchemist.workspace.manager import ShadowManager
from alchemist.workspace.orchestrator import PromptOrchestrator


async def async_main():
    # Setup initial logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("alchemist.daemon")
    
    # Check lock
    lock = DaemonLock()
    try:
        lock.acquire()
    except LockAcquisitionError as e:
        logger.error(str(e))
        sys.exit(1)

    try:
        ensure_runtime_dir()
        ensure_config_dir()
        
        lifecycle = LifecycleManager(grace_period_seconds=15.0)
        lifecycle.setup_signal_handlers()

        # Workspace & Orchestrator components
        shadow_manager = ShadowManager()
        lifecycle.register_cleanup_callback(shadow_manager.cleanup_all)

        engine = StubAssistantEngine()
        broadcaster = Broadcaster()
        job_tracker = ActiveJobTracker()

        orchestrator = PromptOrchestrator(
            shadow_manager=shadow_manager,
            engine=engine,
            job_tracker=job_tracker,
            broadcaster=broadcaster,
        )

        registry = build_default_registry(lifecycle, get_socket_path(), orchestrator=orchestrator)
        dispatcher = RpcDispatcher(registry)
        server = IpcServer(lifecycle, dispatcher.dispatch)
        
        # Register server shutdown with lifecycle
        lifecycle.register_cleanup_callback(server.stop)
        
        # Start server
        await server.start()
        
        # Wait until lifecycle says it's time to shutdown
        await lifecycle.wait_for_shutdown()
        
    finally:
        logger.info("Releasing daemon lock.")
        lock.release()


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()

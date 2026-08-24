"""SQLite ledger for persisting telemetry and quota usage."""

import asyncio
import logging
from typing import Any, Dict, List, Optional
import aiosqlite

from alchemist.daemon.paths import get_ledger_path

logger = logging.getLogger(__name__)

class SqliteLedger:
    """Manages the aiosqlite database connection with WAL mode."""
    def __init__(self):
        self.db_path = get_ledger_path()
        self._db: Optional[aiosqlite.Connection] = None
        self._flush_task: Optional[asyncio.Task] = None
        self._pending_metrics: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._running = False

    async def initialize(self) -> None:
        """Initialize the database and start the batch worker."""
        # Ensure parent dir exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._db = await aiosqlite.connect(self.db_path)
        
        # Apply WAL mode pragmas
        await self._db.execute("PRAGMA journal_mode = WAL;")
        await self._db.execute("PRAGMA synchronous = NORMAL;")
        await self._db.execute("PRAGMA busy_timeout = 5000;")
        
        # Create tables if not exist
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER
            )
        """)
        await self._db.commit()
        
        self._running = True
        self._flush_task = asyncio.create_task(self._batch_worker())
        logger.info(f"SQLite ledger initialized at {self.db_path}")

    async def record_telemetry(self, provider: str, model: str, usage: Dict[str, int]) -> None:
        """Queue a telemetry record for deferred commit."""
        import time
        async with self._lock:
            self._pending_metrics.append({
                "timestamp": time.time(),
                "provider": provider,
                "model": model,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            })

    async def force_flush(self) -> None:
        """Force a flush of all pending metrics to the database."""
        async with self._lock:
            metrics_to_flush = self._pending_metrics[:]
            self._pending_metrics.clear()
            
        if not metrics_to_flush or not self._db:
            return

        try:
            await self._db.executemany("""
                INSERT INTO telemetry (
                    timestamp, provider, model, prompt_tokens, completion_tokens, total_tokens
                ) VALUES (
                    :timestamp, :provider, :model, :prompt_tokens, :completion_tokens, :total_tokens
                )
            """, metrics_to_flush)
            await self._db.commit()
        except Exception as e:
            logger.error(f"Failed to flush telemetry to SQLite: {e}")

    async def _batch_worker(self) -> None:
        """Background worker that flushes metrics every 2 seconds."""
        try:
            while self._running:
                await asyncio.sleep(2.0)
                await self.force_flush()
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        """Flush remaining metrics and close the database connection."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
                
        await self.force_flush()
        
        if self._db:
            try:
                await self._db.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            except Exception as e:
                logger.warning(f"Failed to checkpoint WAL: {e}")
            await self._db.close()
            self._db = None

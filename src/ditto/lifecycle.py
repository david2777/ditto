"""Application lifecycle management, global state, and background tasks."""

import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from loguru import logger
from fastapi import FastAPI

from ditto import database, notion

# Initialize QuoteManager
quote_manager = database.QuoteManager()

# Global State
START_TIME = time.time()
RECENT_CONNECTIONS = deque(maxlen=10)


async def schedule_daily_sync():
    """Background task that syncs the Notion database every day at midnight.

    Runs in an infinite loop, sleeping until the next midnight before triggering a sync. On failure the loop
    pauses for 60 seconds to prevent rapid retries.

    Raises:
        asyncio.CancelledError: Propagated when the task is cancelled during shutdown.
    """
    while True:
        # Calculate time until next midnight
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        next_run = datetime(year=tomorrow.year, month=tomorrow.month, day=tomorrow.day, hour=0, minute=0, second=0)

        sleep_duration = (next_run - now).total_seconds()
        logger.info(f"Next Notion sync scheduled in {sleep_duration:.2f} seconds (at {next_run})")

        try:
            await asyncio.sleep(sleep_duration)
            logger.info("Starting scheduled daily Notion sync...")
            await notion.sync_notion_db(quote_manager)
            logger.info("Daily Notion sync completed.")
        except asyncio.CancelledError:
            logger.info("Daily sync task cancelled.")
            raise
        except Exception as e:
            logger.error(f"Error in daily sync task: {e}")
            # Prevent rapid failure loops
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager that handles startup and shutdown tasks.

    On startup, performs an initial Notion database sync and launches the daily sync background task.
    On shutdown, cancels the background task and waits for it to finish.

    Args:
        app: The FastAPI application instance.

    Yields:
        None: Control is yielded to the application between startup and shutdown.
    """
    # Startup: Sync data from Notion
    logger.info("Starting up: Syncing Notion data...")
    try:
        await notion.sync_notion_db(quote_manager)
    except Exception as e:
        logger.error(f"Failed to sync Notion data on startup: {e}")

    # Start daily sync task
    sync_task = asyncio.create_task(schedule_daily_sync())

    # Yield control to the application
    yield

    # Handle shutdown
    logger.info("Shutting down: Cancelling background tasks...")
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        logger.info("Daily sync task cancelled successfully.")
    except Exception as e:
        # Catch unexpected crashes that happened during the task's life
        logger.error(f"Daily sync task failed with an error: {e}")

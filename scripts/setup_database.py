#!/usr/bin/env python
"""Initialize the papersearch database."""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from papersearch.config import get_settings
from papersearch.db.schema import initialize_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


async def main():
    """Initialize database."""
    settings = get_settings()
    logger.info(f"Setting up database at {settings.database_path}")

    await initialize_database(settings.database_path)

    logger.info("Database setup complete!")
    logger.info(f"Database location: {settings.database_path}")


if __name__ == "__main__":
    asyncio.run(main())

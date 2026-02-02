#!/usr/bin/env python
"""Run paper collection pipeline."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from papersearch.config import get_settings
from papersearch.pipeline import run_daily_collection


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run paper collection pipeline")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without storing papers in database",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger = logging.getLogger(__name__)

    try:
        settings = get_settings()
        stats = asyncio.run(run_daily_collection(settings, dry_run=args.dry_run))

        logger.info("Collection completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Collection failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

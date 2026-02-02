#!/usr/bin/env python
"""Test MCP server tools."""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from papersearch.config import get_settings
from papersearch.db.repository import PaperRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


async def test_repository():
    """Test basic repository operations."""
    settings = get_settings()
    repo = PaperRepository(settings.database_path)

    logger.info("Testing repository operations...")

    # Test 1: List recent papers
    logger.info("\nTest 1: List recent papers (7 days)")
    papers = await repo.list_recent_papers(days=7, limit=5)
    logger.info(f"Found {len(papers)} recent papers")
    for paper in papers:
        logger.info(f"  - {paper.title[:60]}... (ID: {paper.id})")

    # Test 2: Search papers
    if papers:
        logger.info("\nTest 2: Search papers")
        results = await repo.search_papers("reinforcement learning", limit=5)
        logger.info(f"Found {len(results)} papers matching 'reinforcement learning'")
        for result in results:
            logger.info(f"  - {result.paper.title[:60]}... (ID: {result.paper.id})")

        # Test 3: Get paper details
        if papers:
            logger.info("\nTest 3: Get paper details")
            paper = await repo.get_paper(papers[0].id)
            logger.info(f"Paper: {paper.title}")
            logger.info(f"Authors: {', '.join(a.name for a in paper.authors[:3])}")
            logger.info(f"Abstract: {paper.abstract[:100]}...")
            if paper.ai_summary:
                logger.info(f"Summary: {paper.ai_summary[:100]}...")

        # Test 4: Find related papers
        if papers and papers[0].embedding:
            logger.info("\nTest 4: Find related papers")
            related = await repo.find_related_papers(papers[0].id, limit=3)
            logger.info(f"Found {len(related)} related papers")
            for result in related:
                score = result.score * 100 if result.score else 0
                logger.info(
                    f"  - {result.paper.title[:60]}... (Similarity: {score:.1f}%)"
                )

    # Test 5: Daily summary
    logger.info("\nTest 5: Get daily summary")
    summary = await repo.get_daily_summary()
    logger.info(f"Date: {summary.date}")
    logger.info(f"Total papers: {summary.total_papers}")
    logger.info(f"Papers by source: {summary.papers_by_source}")
    logger.info(f"Top categories: {summary.top_categories}")
    logger.info(f"Highlights: {len(summary.highlights)}")

    logger.info("\nAll tests completed!")


if __name__ == "__main__":
    asyncio.run(test_repository())

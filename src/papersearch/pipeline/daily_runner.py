"""Daily collection pipeline orchestration."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from ..collectors import ArxivCollector, Deduplicator, RSSCollector
from ..config import Settings
from ..db.models import Paper
from ..processing import KeyIdeasExtractor, Summarizer
from ..zotero_client import ZoteroClient

logger = logging.getLogger(__name__)


async def run_daily_collection(
    settings: Settings,
    dry_run: bool = False,
) -> dict[str, int]:
    """Run daily paper collection pipeline.

    Steps:
    1. Collect from sources (arXiv, RSS)
    2. Deduplicate against Zotero library
    3. Process with LLM (summarize + extract key ideas)
    4. Store in Zotero with summaries as notes

    Args:
        settings: Application settings
        dry_run: If True, don't store papers in Zotero

    Returns:
        Statistics dict with counts
    """
    logger.info("=" * 60)
    logger.info("Starting daily collection pipeline")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 60)

    # Initialize Zotero client
    if not dry_run:
        try:
            settings.validate_api_keys()
            zotero_client = ZoteroClient(settings)
            logger.info("✓ Connected to Zotero")
        except Exception as e:
            logger.error(f"Failed to initialize Zotero client: {e}")
            raise
    else:
        zotero_client = None

    stats = {
        "collected": 0,
        "duplicates": 0,
        "stored": 0,
        "processed": 0,
        "errors": 0,
    }

    try:
        # Step 1: Collect papers
        logger.info("\n" + "=" * 60)
        logger.info("Step 1: Collecting papers from sources")
        logger.info("=" * 60)

        papers = []

        # Collect from arXiv
        logger.info("\nCollecting from arXiv...")
        arxiv_collector = ArxivCollector(
            lookback_hours=settings.lookback_hours,
            rate_limit=settings.arxiv_rate_limit,
        )
        arxiv_papers = await arxiv_collector.collect()
        papers.extend(arxiv_papers)
        logger.info(f"✓ Collected {len(arxiv_papers)} papers from arXiv")

        # Collect from RSS
        logger.info("\nCollecting from RSS feeds...")
        rss_collector = RSSCollector(
            lookback_hours=settings.lookback_hours,
        )
        rss_papers = await rss_collector.collect()
        papers.extend(rss_papers)
        logger.info(f"✓ Collected {len(rss_papers)} papers from RSS")

        stats["collected"] = len(papers)
        logger.info(f"\nTotal papers collected: {len(papers)}")

        if len(papers) == 0:
            logger.info("No new papers found. Exiting.")
            return stats

        # Step 2: Deduplicate
        logger.info("\n" + "=" * 60)
        logger.info("Step 2: Deduplicating papers")
        logger.info("=" * 60)

        unique_papers = []

        if not dry_run:
            deduplicator = Deduplicator(zotero_client)

            for paper in papers:
                is_dup, dup_key = deduplicator.is_duplicate(paper)
                if is_dup:
                    stats["duplicates"] += 1
                    logger.debug(f"Duplicate: {paper.title[:60]}...")
                else:
                    unique_papers.append(paper)
        else:
            unique_papers = papers
            logger.info("[DRY RUN] Skipping deduplication check")

        logger.info(f"✓ Filtered out {stats['duplicates']} duplicates")
        logger.info(f"✓ {len(unique_papers)} unique papers remaining")

        if len(unique_papers) == 0:
            logger.info("No unique papers to process. Exiting.")
            return stats

        # Step 3: Process with LLM (if enabled)
        if settings.summarization_enabled:
            logger.info("\n" + "=" * 60)
            logger.info("Step 3: Processing papers with LLM")
            logger.info("=" * 60)

            try:
                summarizer = Summarizer(settings)
                extractor = KeyIdeasExtractor(settings)

                logger.info("Generating summaries...")
                papers_data = [(p.title, p.abstract) for p in unique_papers]
                summaries = await summarizer.batch_summarize(papers_data)

                logger.info("Extracting key ideas...")
                key_ideas_list = await extractor.batch_extract(papers_data)

                # Update papers with summaries
                for paper, summary, key_ideas in zip(unique_papers, summaries, key_ideas_list):
                    if summary:
                        paper.ai_summary = summary
                    if key_ideas:
                        paper.key_ideas = key_ideas
                    paper.processed_at = datetime.now(timezone.utc)
                    stats["processed"] += 1

                logger.info(f"✓ Processed {stats['processed']} papers with LLM")

            except Exception as e:
                logger.error(f"Error in LLM processing: {e}")
                logger.info("Continuing without LLM processing...")
        else:
            logger.info("\n" + "=" * 60)
            logger.info("Step 3: Skipping LLM processing (disabled)")
            logger.info("=" * 60)

        # Step 4: Store in Zotero
        if not dry_run:
            logger.info("\n" + "=" * 60)
            logger.info("Step 4: Storing papers in Zotero")
            logger.info("=" * 60)

            for paper in unique_papers:
                try:
                    item_key = zotero_client.add_paper(paper)
                    stats["stored"] += 1
                    logger.debug(f"Stored: {paper.title[:60]}...")
                except Exception as e:
                    logger.error(f"Error storing paper: {e}")
                    stats["errors"] += 1

            logger.info(f"✓ Stored {stats['stored']} papers in Zotero")
        else:
            logger.info("\n[DRY RUN] Skipping Zotero storage")
            stats["stored"] = len(unique_papers)

        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("Pipeline completed successfully!")
        logger.info("=" * 60)
        logger.info(f"Papers collected:  {stats['collected']}")
        logger.info(f"Duplicates found:  {stats['duplicates']}")
        logger.info(f"Papers processed:  {stats['processed']}")
        logger.info(f"Papers stored:     {stats['stored']}")
        logger.info(f"Errors:            {stats['errors']}")
        logger.info("=" * 60)

        return stats

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        raise

#!/usr/bin/env python
"""Bulk add seminal papers to Zotero from a list of arXiv IDs."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import arxiv

from papersearch.config import get_settings
from papersearch.db.models import Author, Category, Paper
from papersearch.processing import KeyIdeasExtractor, Summarizer
from papersearch.zotero_client import ZoteroClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def load_arxiv_ids(file_path: Path) -> list[str]:
    """Load arXiv IDs from file.

    Args:
        file_path: Path to file with arXiv IDs (one per line, # for comments)

    Returns:
        List of arXiv IDs
    """
    arxiv_ids = []

    with open(file_path) as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Extract arXiv ID (handle various formats)
            if "arxiv.org" in line:
                # Extract from URL
                arxiv_id = line.split("/")[-1].split(".pdf")[0]
            else:
                # Assume it's just the ID
                arxiv_id = line.split()[0]  # Take first token (before any comment)

            arxiv_ids.append(arxiv_id)

    return arxiv_ids


async def fetch_paper_from_arxiv(arxiv_id: str) -> Paper:
    """Fetch paper metadata from arXiv.

    Args:
        arxiv_id: arXiv ID

    Returns:
        Paper object
    """
    search = arxiv.Search(id_list=[arxiv_id])

    try:
        result = next(search.results())
    except StopIteration:
        raise ValueError(f"Paper not found on arXiv: {arxiv_id}")

    # Convert to Paper model
    authors = [
        Author(name=author.name, normalized_name=author.name.lower().strip())
        for author in result.authors
    ]

    categories = [Category(name=cat, source="arxiv") for cat in result.categories]

    doi = result.doi if hasattr(result, "doi") else None

    return Paper(
        arxiv_id=arxiv_id,
        doi=doi,
        url=result.entry_id,
        title=result.title,
        abstract=result.summary,
        publication_date=result.published,
        source="arxiv:seminal",
        authors=authors,
        categories=categories,
    )


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Bulk add seminal papers to Zotero")
    parser.add_argument(
        "--papers",
        type=Path,
        default=Path(__file__).parent.parent / "config" / "seminal_papers.txt",
        help="Path to file with arXiv IDs",
    )
    parser.add_argument(
        "--skip-summaries",
        action="store_true",
        help="Skip LLM summarization (faster, cheaper)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually add to Zotero",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    logging.getLogger().setLevel(getattr(logging, args.log_level))

    logger.info("=" * 60)
    logger.info("Bulk Adding Seminal Papers")
    logger.info(f"Papers file: {args.papers}")
    logger.info(f"Skip summaries: {args.skip_summaries}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 60)

    # Load settings
    settings = get_settings()

    # Initialize Zotero client
    if not args.dry_run:
        try:
            settings.validate_api_keys()
            zotero_client = ZoteroClient(settings)
            logger.info("✓ Connected to Zotero")
        except Exception as e:
            logger.error(f"Failed to initialize Zotero: {e}")
            return 1
    else:
        zotero_client = None

    # Load arXiv IDs
    try:
        arxiv_ids = load_arxiv_ids(args.papers)
        logger.info(f"Loaded {len(arxiv_ids)} arXiv IDs from {args.papers}")
    except Exception as e:
        logger.error(f"Failed to load paper IDs: {e}")
        return 1

    if len(arxiv_ids) == 0:
        logger.error("No arXiv IDs found in file")
        return 1

    # Fetch papers
    logger.info("\n" + "=" * 60)
    logger.info("Step 1: Fetching papers from arXiv")
    logger.info("=" * 60)

    papers = []
    for i, arxiv_id in enumerate(arxiv_ids, 1):
        try:
            logger.info(f"[{i}/{len(arxiv_ids)}] Fetching {arxiv_id}...")
            paper = await fetch_paper_from_arxiv(arxiv_id)
            papers.append(paper)
            logger.info(f"  ✓ {paper.title[:60]}...")

            # Rate limiting
            if i < len(arxiv_ids):
                await asyncio.sleep(1)  # 1 req/sec for arXiv

        except Exception as e:
            logger.error(f"  ✗ Failed to fetch {arxiv_id}: {e}")
            continue

    logger.info(f"\n✓ Successfully fetched {len(papers)}/{len(arxiv_ids)} papers")

    if len(papers) == 0:
        logger.error("No papers fetched successfully")
        return 1

    # Check for duplicates
    if not args.dry_run:
        logger.info("\n" + "=" * 60)
        logger.info("Step 2: Checking for duplicates in Zotero")
        logger.info("=" * 60)

        unique_papers = []
        duplicates = 0

        for paper in papers:
            try:
                existing = zotero_client.find_duplicate(paper)
                if existing:
                    logger.info(f"  ⊘ Duplicate: {paper.title[:60]}...")
                    duplicates += 1
                else:
                    unique_papers.append(paper)
            except Exception as e:
                logger.warning(f"  ? Error checking duplicate: {e}")
                unique_papers.append(paper)  # Add anyway if check fails

        logger.info(f"\n✓ {len(unique_papers)} unique papers, {duplicates} duplicates")
        papers = unique_papers

    # Generate summaries
    if not args.skip_summaries and settings.summarization_enabled:
        logger.info("\n" + "=" * 60)
        logger.info("Step 3: Generating AI summaries")
        logger.info("=" * 60)

        try:
            summarizer = Summarizer(settings)
            extractor = KeyIdeasExtractor(settings)

            logger.info("Generating summaries...")
            papers_data = [(p.title, p.abstract) for p in papers]
            summaries = await summarizer.batch_summarize(papers_data, batch_size=5)

            logger.info("Extracting key ideas...")
            key_ideas_list = await extractor.batch_extract(papers_data, batch_size=5)

            # Update papers
            for paper, summary, key_ideas in zip(papers, summaries, key_ideas_list):
                if summary:
                    paper.ai_summary = summary
                if key_ideas:
                    paper.key_ideas = key_ideas

            logger.info("✓ Generated summaries for all papers")

        except Exception as e:
            logger.error(f"Error generating summaries: {e}")
            logger.info("Continuing without summaries...")
    else:
        logger.info("\n" + "=" * 60)
        logger.info("Step 3: Skipping AI summaries")
        logger.info("=" * 60)

    # Add to Zotero
    if not args.dry_run:
        logger.info("\n" + "=" * 60)
        logger.info("Step 4: Adding papers to Zotero")
        logger.info("=" * 60)

        added = 0
        errors = 0

        for i, paper in enumerate(papers, 1):
            try:
                logger.info(f"[{i}/{len(papers)}] Adding: {paper.title[:60]}...")
                item_key = zotero_client.add_paper(paper)
                added += 1
                logger.info(f"  ✓ Added with key: {item_key}")
            except Exception as e:
                logger.error(f"  ✗ Error adding paper: {e}")
                errors += 1

        logger.info("\n" + "=" * 60)
        logger.info("Completed!")
        logger.info("=" * 60)
        logger.info(f"Papers added:   {added}")
        logger.info(f"Errors:         {errors}")
        logger.info("=" * 60)

    else:
        logger.info("\n[DRY RUN] Would have added {len(papers)} papers to Zotero")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

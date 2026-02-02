"""arXiv paper collector."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import arxiv
import yaml

from ..db.models import Author, Category, Paper
from .base import BaseCollector

logger = logging.getLogger(__name__)


class ArxivCollector(BaseCollector):
    """Collector for arXiv papers."""

    def __init__(
        self,
        lookback_hours: int = 24,
        rate_limit: float = 1.0,
        config_path: Optional[Path] = None,
    ):
        """Initialize arXiv collector.

        Args:
            lookback_hours: How many hours to look back
            rate_limit: Requests per second (arXiv requires max 1 req/3s)
            config_path: Path to queries.yaml config file
        """
        super().__init__(lookback_hours)
        self.rate_limit = rate_limit
        self.config_path = config_path or Path(__file__).parent.parent.parent.parent / "config" / "queries.yaml"
        self._load_config()

    def _load_config(self) -> None:
        """Load search configuration from YAML."""
        if not self.config_path.exists():
            logger.warning(f"Config file not found: {self.config_path}, using defaults")
            self.categories = ["cs.LG", "cs.RO", "cs.AI"]
            self.keywords = ["reinforcement learning", "robot learning", "robotics"]
            self.max_results_per_query = 50
            return

        with open(self.config_path) as f:
            config = yaml.safe_load(f)

        arxiv_config = config.get("arxiv", {})
        self.categories = arxiv_config.get("categories", ["cs.LG", "cs.RO", "cs.AI"])
        self.keywords = arxiv_config.get("keywords", ["reinforcement learning"])
        self.max_results_per_query = arxiv_config.get("max_results_per_query", 50)

    @property
    def source_name(self) -> str:
        """Get source name."""
        return "arxiv"

    async def collect(self) -> list[Paper]:
        """Collect papers from arXiv.

        Returns:
            List of collected papers
        """
        logger.info("Starting arXiv collection")
        cutoff_date = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)
        papers = []

        # Build search queries
        queries = self._build_queries()
        logger.info(f"Running {len(queries)} arXiv queries")

        for i, query in enumerate(queries):
            logger.debug(f"Query {i+1}/{len(queries)}: {query}")

            # Rate limiting
            if i > 0:
                await asyncio.sleep(1.0 / self.rate_limit)

            # Search arXiv
            search = arxiv.Search(
                query=query,
                max_results=self.max_results_per_query,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )

            try:
                for result in search.results():
                    # Check if paper is within lookback window
                    if result.published < cutoff_date:
                        break  # Results are sorted by date, so we can stop

                    paper = self._result_to_paper(result)
                    papers.append(paper)

            except Exception as e:
                logger.error(f"Error searching arXiv with query '{query}': {e}")
                continue

        logger.info(f"Collected {len(papers)} papers from arXiv")
        return papers

    def _build_queries(self) -> list[str]:
        """Build arXiv search queries.

        Returns:
            List of query strings
        """
        queries = []

        # Category-based queries
        for category in self.categories:
            queries.append(f"cat:{category}")

        # Keyword-based queries
        for keyword in self.keywords:
            # Search in title and abstract
            queries.append(f'ti:"{keyword}" OR abs:"{keyword}"')

        return queries

    def _result_to_paper(self, result: arxiv.Result) -> Paper:
        """Convert arXiv result to Paper model.

        Args:
            result: arXiv search result

        Returns:
            Paper model
        """
        # Extract arXiv ID from URL
        arxiv_id = result.entry_id.split("/")[-1]

        # Extract authors
        authors = [
            Author(
                name=author.name,
                normalized_name=author.name.lower().strip(),
            )
            for author in result.authors
        ]

        # Extract categories
        categories = [
            Category(name=cat, source="arxiv") for cat in result.categories
        ]

        # Get DOI if available
        doi = result.doi if hasattr(result, "doi") else None

        return Paper(
            arxiv_id=arxiv_id,
            doi=doi,
            url=result.entry_id,
            title=result.title,
            abstract=result.summary,
            publication_date=result.published,
            source="arxiv",
            collected_at=datetime.now(timezone.utc),
            authors=authors,
            categories=categories,
        )

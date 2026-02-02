"""RSS feed collector."""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import feedparser
import httpx
import yaml

from ..db.models import Author, Category, Paper
from .base import BaseCollector

logger = logging.getLogger(__name__)


class RSSCollector(BaseCollector):
    """Collector for RSS feeds."""

    def __init__(
        self,
        lookback_hours: int = 24,
        config_path: Optional[Path] = None,
    ):
        """Initialize RSS collector.

        Args:
            lookback_hours: How many hours to look back
            config_path: Path to rss_feeds.yaml config file
        """
        super().__init__(lookback_hours)
        self.config_path = config_path or Path(__file__).parent.parent.parent.parent / "config" / "rss_feeds.yaml"
        self._load_config()

    def _load_config(self) -> None:
        """Load RSS feed configuration from YAML."""
        if not self.config_path.exists():
            logger.warning(f"Config file not found: {self.config_path}, using defaults")
            self.feeds = []
            return

        with open(self.config_path) as f:
            config = yaml.safe_load(f)

        self.feeds = config.get("feeds", [])

    @property
    def source_name(self) -> str:
        """Get source name."""
        return "rss"

    async def collect(self) -> list[Paper]:
        """Collect papers from RSS feeds.

        Returns:
            List of collected papers
        """
        logger.info("Starting RSS collection")
        cutoff_date = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)
        papers = []

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for feed_config in self.feeds:
                feed_url = feed_config["url"]
                feed_name = feed_config["name"]

                logger.debug(f"Fetching RSS feed: {feed_name}")

                try:
                    response = await client.get(feed_url)
                    response.raise_for_status()

                    feed = feedparser.parse(response.text)

                    for entry in feed.entries:
                        # Parse publication date
                        pub_date = self._parse_date(entry)
                        if not pub_date or pub_date < cutoff_date:
                            continue

                        paper = self._entry_to_paper(entry, feed_name)
                        if paper:
                            papers.append(paper)

                except Exception as e:
                    logger.error(f"Error fetching RSS feed {feed_name}: {e}")
                    continue

        logger.info(f"Collected {len(papers)} papers from RSS feeds")
        return papers

    def _parse_date(self, entry: feedparser.FeedParserDict) -> Optional[datetime]:
        """Parse publication date from RSS entry.

        Args:
            entry: RSS feed entry

        Returns:
            Publication date or None (timezone-aware)
        """
        # Try different date fields
        for date_field in ["published_parsed", "updated_parsed", "created_parsed"]:
            if hasattr(entry, date_field):
                time_struct = getattr(entry, date_field)
                if time_struct:
                    try:
                        # Create timezone-aware datetime
                        dt = datetime(*time_struct[:6], tzinfo=timezone.utc)
                        return dt
                    except Exception:
                        pass

        return None

    def _entry_to_paper(
        self, entry: feedparser.FeedParserDict, feed_name: str
    ) -> Optional[Paper]:
        """Convert RSS entry to Paper model.

        Args:
            entry: RSS feed entry
            feed_name: Name of the RSS feed

        Returns:
            Paper model or None if invalid
        """
        # Get title
        title = entry.get("title", "").strip()
        if not title:
            return None

        # Get link
        url = entry.get("link", "")
        if not url:
            return None

        # Get abstract/summary
        abstract = ""
        if "summary" in entry:
            abstract = entry.summary
        elif "description" in entry:
            abstract = entry.description
        elif "content" in entry:
            # Take first content block
            if entry.content:
                abstract = entry.content[0].get("value", "")

        # Clean HTML tags from abstract
        abstract = self._clean_html(abstract)

        # Parse date
        pub_date = self._parse_date(entry)
        if not pub_date:
            pub_date = datetime.now(timezone.utc)

        # Extract authors
        authors = []
        if "author" in entry:
            authors.append(
                Author(
                    name=entry.author,
                    normalized_name=entry.author.lower().strip(),
                )
            )
        elif "authors" in entry:
            for author_dict in entry.authors:
                name = author_dict.get("name", "")
                if name:
                    authors.append(
                        Author(
                            name=name,
                            normalized_name=name.lower().strip(),
                        )
                    )

        # Generate synthetic ID from URL
        synthetic_id = self._generate_id(url)

        # Check if this is an arXiv RSS entry
        arxiv_id = None
        if "arxiv.org" in url:
            arxiv_id = url.split("/")[-1]

        # Create category from feed name
        categories = [Category(name=feed_name, source="rss")]

        return Paper(
            arxiv_id=arxiv_id,
            doi=None,
            url=url,
            title=title,
            abstract=abstract,
            publication_date=pub_date,
            source=f"rss:{feed_name}",
            collected_at=datetime.now(timezone.utc),
            authors=authors,
            categories=categories,
        )

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags from text.

        Args:
            text: Text with HTML tags

        Returns:
            Cleaned text
        """
        # Simple HTML tag removal
        import re

        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _generate_id(self, url: str) -> str:
        """Generate synthetic ID from URL.

        Args:
            url: Paper URL

        Returns:
            Synthetic ID
        """
        return hashlib.md5(url.encode()).hexdigest()[:16]

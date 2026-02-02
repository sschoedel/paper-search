"""Paper deduplication logic."""

import logging
from typing import Optional

from thefuzz import fuzz

from ..db.models import Paper
from ..zotero_client import ZoteroClient

logger = logging.getLogger(__name__)


class Deduplicator:
    """Deduplicator for papers using multi-tier strategy."""

    def __init__(self, zotero_client: ZoteroClient):
        """Initialize deduplicator.

        Args:
            zotero_client: Zotero API client
        """
        self.zotero_client = zotero_client

    def is_duplicate(self, paper: Paper) -> tuple[bool, Optional[str]]:
        """Check if paper is a duplicate.

        Args:
            paper: Paper to check

        Returns:
            Tuple of (is_duplicate, duplicate_item_key)
        """
        duplicate_key = self.zotero_client.find_duplicate(paper)
        if duplicate_key:
            logger.debug(f"Found duplicate: {duplicate_key}")
            return True, duplicate_key

        return False, None

    def _is_title_similar(self, title1: str, title2: str) -> bool:
        """Check if two titles are similar using fuzzy matching.

        Args:
            title1: First title
            title2: Second title

        Returns:
            True if similar
        """
        similarity = fuzz.ratio(title1.lower(), title2.lower()) / 100.0
        return similarity >= self.title_threshold

    def _is_abstract_similar(self, abstract1: str, abstract2: str) -> bool:
        """Check if two abstracts are similar.

        Args:
            abstract1: First abstract
            abstract2: Second abstract

        Returns:
            True if similar
        """
        # Compare first 200 characters
        snippet1 = abstract1[:200].lower()
        snippet2 = abstract2[:200].lower()

        similarity = fuzz.ratio(snippet1, snippet2) / 100.0
        return similarity >= self.abstract_threshold

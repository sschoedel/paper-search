"""Collectors module for papersearch."""

from .arxiv_collector import ArxivCollector
from .base import BaseCollector
from .deduplicator import Deduplicator
from .rss_collector import RSSCollector

__all__ = [
    "BaseCollector",
    "ArxivCollector",
    "RSSCollector",
    "Deduplicator",
]

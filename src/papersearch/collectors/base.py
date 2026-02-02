"""Base collector interface."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from ..db.models import Paper


class BaseCollector(ABC):
    """Abstract base class for paper collectors."""

    def __init__(self, lookback_hours: int = 24):
        """Initialize collector.

        Args:
            lookback_hours: How many hours to look back for papers
        """
        self.lookback_hours = lookback_hours

    @abstractmethod
    async def collect(self) -> list[Paper]:
        """Collect papers from source.

        Returns:
            List of collected papers
        """
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Get source name for this collector."""
        pass

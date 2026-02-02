"""Pydantic models for papersearch data structures."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class Author(BaseModel):
    """Author model."""

    id: Optional[int] = None
    name: str
    normalized_name: str


class Category(BaseModel):
    """Category/tag model."""

    id: Optional[int] = None
    name: str
    source: str  # 'arxiv' or 'custom'


class Paper(BaseModel):
    """Paper model with all metadata."""

    id: Optional[int] = None
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None
    url: str
    title: str
    abstract: str
    publication_date: datetime
    source: str  # 'arxiv', 'rss', etc.
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None

    # AI-generated content
    ai_summary: Optional[str] = None
    key_ideas: Optional[list[str]] = None
    embedding: Optional[bytes] = None

    # Relationships (populated by joins)
    authors: list[Author] = Field(default_factory=list)
    categories: list[Category] = Field(default_factory=list)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            bytes: lambda v: None,  # Don't serialize embeddings to JSON
        }


class CollectionRun(BaseModel):
    """Collection run tracking."""

    id: Optional[int] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: str  # 'running', 'completed', 'failed'
    papers_collected: int = 0
    papers_processed: int = 0
    error_message: Optional[str] = None


class PaperSearchResult(BaseModel):
    """Search result with relevance scoring."""

    paper: Paper
    score: Optional[float] = None
    match_snippet: Optional[str] = None


class DailySummary(BaseModel):
    """Daily digest summary."""

    date: str
    total_papers: int
    papers_by_source: dict[str, int]
    top_categories: list[tuple[str, int]]
    highlights: list[Paper]

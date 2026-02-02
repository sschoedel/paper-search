"""Tests for collectors."""

import pytest
from datetime import datetime

from papersearch.db.models import Paper, Author, Category


def test_paper_model():
    """Test Paper model creation."""
    paper = Paper(
        arxiv_id="2301.00001",
        url="https://arxiv.org/abs/2301.00001",
        title="Test Paper",
        abstract="This is a test abstract.",
        publication_date=datetime.utcnow(),
        source="arxiv",
        authors=[Author(name="John Doe", normalized_name="john doe")],
        categories=[Category(name="cs.LG", source="arxiv")],
    )

    assert paper.title == "Test Paper"
    assert len(paper.authors) == 1
    assert paper.authors[0].name == "John Doe"

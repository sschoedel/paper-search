"""Database repository for paper operations."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiosqlite
import numpy as np

from .models import Author, Category, CollectionRun, DailySummary, Paper, PaperSearchResult

logger = logging.getLogger(__name__)


class PaperRepository:
    """Repository for paper database operations."""

    def __init__(self, db_path: Path):
        """Initialize repository.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path

    def _connect(self):
        """Get database connection context manager."""
        return aiosqlite.connect(self.db_path)

    async def _setup_connection(self, conn: aiosqlite.Connection) -> None:
        """Configure connection settings."""
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")

    # Paper CRUD operations

    async def create_paper(self, paper: Paper) -> int:
        """Create a new paper.

        Args:
            paper: Paper to create

        Returns:
            ID of created paper
        """
        async with self._connect() as db:
            await self._setup_connection(db)
            cursor = await db.execute(
                """
                INSERT INTO papers (
                    arxiv_id, doi, url, title, abstract, publication_date,
                    source, collected_at, processed_at, ai_summary, key_ideas, embedding
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    paper.arxiv_id,
                    paper.doi,
                    paper.url,
                    paper.title,
                    paper.abstract,
                    paper.publication_date.isoformat(),
                    paper.source,
                    paper.collected_at.isoformat(),
                    paper.processed_at.isoformat() if paper.processed_at else None,
                    paper.ai_summary,
                    json.dumps(paper.key_ideas) if paper.key_ideas else None,
                    paper.embedding,
                ),
            )
            await db.commit()
            paper_id = cursor.lastrowid

            # Insert authors
            for author in paper.authors:
                author_id = await self._get_or_create_author(db, author.name)
                await db.execute(
                    "INSERT INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, ?)",
                    (paper_id, author_id, 0),
                )

            # Insert categories
            for category in paper.categories:
                category_id = await self._get_or_create_category(
                    db, category.name, category.source
                )
                await db.execute(
                    "INSERT INTO paper_categories (paper_id, category_id) VALUES (?, ?)",
                    (paper_id, category_id),
                )

            await db.commit()
            return paper_id

    async def get_paper(self, paper_id: int) -> Optional[Paper]:
        """Get paper by ID.

        Args:
            paper_id: Paper ID

        Returns:
            Paper or None if not found
        """
        async with self._connect() as db:
            await self._setup_connection(db)
            cursor = await db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
            row = await cursor.fetchone()

            if not row:
                return None

            return await self._row_to_paper(db, row)

    async def update_paper(self, paper: Paper) -> None:
        """Update existing paper.

        Args:
            paper: Paper to update (must have id set)
        """
        if not paper.id:
            raise ValueError("Paper must have id set for update")

        async with self._connect() as db:
            await self._setup_connection(db)
            await db.execute(
                """
                UPDATE papers SET
                    arxiv_id = ?, doi = ?, url = ?, title = ?, abstract = ?,
                    publication_date = ?, source = ?, collected_at = ?, processed_at = ?,
                    ai_summary = ?, key_ideas = ?, embedding = ?
                WHERE id = ?
                """,
                (
                    paper.arxiv_id,
                    paper.doi,
                    paper.url,
                    paper.title,
                    paper.abstract,
                    paper.publication_date.isoformat(),
                    paper.source,
                    paper.collected_at.isoformat(),
                    paper.processed_at.isoformat() if paper.processed_at else None,
                    paper.ai_summary,
                    json.dumps(paper.key_ideas) if paper.key_ideas else None,
                    paper.embedding,
                    paper.id,
                ),
            )
            await db.commit()

    async def find_duplicate(self, paper: Paper) -> Optional[int]:
        """Find if paper is a duplicate.

        Args:
            paper: Paper to check

        Returns:
            ID of duplicate paper if found, None otherwise
        """
        async with self._connect() as db:
            await self._setup_connection(db)
            # Check by arxiv_id
            if paper.arxiv_id:
                cursor = await db.execute(
                    "SELECT id FROM papers WHERE arxiv_id = ?", (paper.arxiv_id,)
                )
                row = await cursor.fetchone()
                if row:
                    return row[0]

            # Check by DOI
            if paper.doi:
                cursor = await db.execute("SELECT id FROM papers WHERE doi = ?", (paper.doi,))
                row = await cursor.fetchone()
                if row:
                    return row[0]

            return None

    # Search operations

    async def search_papers(
        self,
        query: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        source: Optional[str] = None,
        limit: int = 10,
    ) -> list[PaperSearchResult]:
        """Full-text search papers.

        Args:
            query: Search query
            date_from: Filter by publication date from
            date_to: Filter by publication date to
            source: Filter by source
            limit: Maximum results

        Returns:
            List of search results
        """
        async with self._connect() as db:
            await self._setup_connection(db)
            sql = """
                SELECT p.*, rank
                FROM papers_fts fts
                JOIN papers p ON p.id = fts.paper_id
                WHERE papers_fts MATCH ?
            """
            params = [query]

            if date_from:
                sql += " AND p.publication_date >= ?"
                params.append(date_from.isoformat())

            if date_to:
                sql += " AND p.publication_date <= ?"
                params.append(date_to.isoformat())

            if source:
                sql += " AND p.source = ?"
                params.append(source)

            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)

            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()

            results = []
            for row in rows:
                paper = await self._row_to_paper(db, row)
                results.append(PaperSearchResult(paper=paper, score=row["rank"]))

            return results

    async def list_recent_papers(
        self,
        days: int = 1,
        source: Optional[str] = None,
        limit: int = 20,
    ) -> list[Paper]:
        """List recent papers chronologically.

        Args:
            days: Number of days to look back
            source: Filter by source
            limit: Maximum results

        Returns:
            List of papers
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        async with self._connect() as db:
            await self._setup_connection(db)
            sql = "SELECT * FROM papers WHERE collected_at >= ?"
            params = [cutoff_date.isoformat()]

            if source:
                sql += " AND source = ?"
                params.append(source)

            sql += " ORDER BY publication_date DESC LIMIT ?"
            params.append(limit)

            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()

            papers = []
            for row in rows:
                papers.append(await self._row_to_paper(db, row))

            return papers

    async def find_related_papers(
        self, paper_id: int, limit: int = 5
    ) -> list[PaperSearchResult]:
        """Find semantically similar papers using embeddings.

        Args:
            paper_id: Reference paper ID
            limit: Maximum results

        Returns:
            List of similar papers with similarity scores
        """
        async with self._connect() as db:
            await self._setup_connection(db)
            # Get reference paper embedding
            cursor = await db.execute(
                "SELECT embedding FROM papers WHERE id = ?", (paper_id,)
            )
            row = await cursor.fetchone()
            if not row or not row["embedding"]:
                return []

            ref_embedding = np.frombuffer(row["embedding"], dtype=np.float32)

            # Get all papers with embeddings
            cursor = await db.execute(
                "SELECT * FROM papers WHERE embedding IS NOT NULL AND id != ?",
                (paper_id,),
            )
            rows = await cursor.fetchall()

            # Calculate similarities
            similarities = []
            for row in rows:
                embedding = np.frombuffer(row["embedding"], dtype=np.float32)
                # Cosine similarity
                similarity = np.dot(ref_embedding, embedding) / (
                    np.linalg.norm(ref_embedding) * np.linalg.norm(embedding)
                )
                similarities.append((row, float(similarity)))

            # Sort by similarity and take top N
            similarities.sort(key=lambda x: x[1], reverse=True)
            similarities = similarities[:limit]

            # Convert to results
            results = []
            for row, score in similarities:
                paper = await self._row_to_paper(db, row)
                results.append(PaperSearchResult(paper=paper, score=score))

            return results

    async def get_daily_summary(self, date: Optional[datetime] = None) -> DailySummary:
        """Get daily digest summary.

        Args:
            date: Date to get summary for (defaults to today)

        Returns:
            Daily summary
        """
        if date is None:
            date = datetime.now(timezone.utc)

        date_str = date.strftime("%Y-%m-%d")
        date_start = f"{date_str} 00:00:00"
        date_end = f"{date_str} 23:59:59"

        async with self._connect() as db:
            await self._setup_connection(db)
            # Total count
            cursor = await db.execute(
                "SELECT COUNT(*) FROM papers WHERE collected_at BETWEEN ? AND ?",
                (date_start, date_end),
            )
            total_papers = (await cursor.fetchone())[0]

            # By source
            cursor = await db.execute(
                """
                SELECT source, COUNT(*) as count
                FROM papers
                WHERE collected_at BETWEEN ? AND ?
                GROUP BY source
                """,
                (date_start, date_end),
            )
            papers_by_source = {row["source"]: row["count"] for row in await cursor.fetchall()}

            # Top categories
            cursor = await db.execute(
                """
                SELECT c.name, COUNT(*) as count
                FROM papers p
                JOIN paper_categories pc ON p.id = pc.paper_id
                JOIN categories c ON pc.category_id = c.id
                WHERE p.collected_at BETWEEN ? AND ?
                GROUP BY c.name
                ORDER BY count DESC
                LIMIT 5
                """,
                (date_start, date_end),
            )
            top_categories = [(row["name"], row["count"]) for row in await cursor.fetchall()]

            # Highlights (recent papers with summaries)
            cursor = await db.execute(
                """
                SELECT * FROM papers
                WHERE collected_at BETWEEN ? AND ?
                AND ai_summary IS NOT NULL
                ORDER BY publication_date DESC
                LIMIT 5
                """,
                (date_start, date_end),
            )
            highlight_rows = await cursor.fetchall()
            highlights = [await self._row_to_paper(db, row) for row in highlight_rows]

            return DailySummary(
                date=date_str,
                total_papers=total_papers,
                papers_by_source=papers_by_source,
                top_categories=top_categories,
                highlights=highlights,
            )

    # Collection run tracking

    async def create_collection_run(self) -> int:
        """Create new collection run.

        Returns:
            Collection run ID
        """
        async with self._connect() as db:
            await self._setup_connection(db)
            cursor = await db.execute(
                """
                INSERT INTO collection_runs (started_at, status)
                VALUES (?, 'running')
                """,
                (datetime.now(timezone.utc).isoformat(),),
            )
            await db.commit()
            return cursor.lastrowid

    async def update_collection_run(
        self,
        run_id: int,
        status: str,
        papers_collected: int = 0,
        papers_processed: int = 0,
        error_message: Optional[str] = None,
    ) -> None:
        """Update collection run.

        Args:
            run_id: Collection run ID
            status: New status
            papers_collected: Number of papers collected
            papers_processed: Number of papers processed
            error_message: Error message if failed
        """
        async with self._connect() as db:
            await self._setup_connection(db)
            await db.execute(
                """
                UPDATE collection_runs
                SET completed_at = ?, status = ?, papers_collected = ?,
                    papers_processed = ?, error_message = ?
                WHERE id = ?
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    status,
                    papers_collected,
                    papers_processed,
                    error_message,
                    run_id,
                ),
            )
            await db.commit()

    # Helper methods

    async def _get_or_create_author(self, db: aiosqlite.Connection, name: str) -> int:
        """Get or create author by name."""
        normalized = name.lower().strip()

        cursor = await db.execute(
            "SELECT id FROM authors WHERE normalized_name = ?", (normalized,)
        )
        row = await cursor.fetchone()

        if row:
            return row[0]

        cursor = await db.execute(
            "INSERT INTO authors (name, normalized_name) VALUES (?, ?)", (name, normalized)
        )
        return cursor.lastrowid

    async def _get_or_create_category(
        self, db: aiosqlite.Connection, name: str, source: str
    ) -> int:
        """Get or create category by name."""
        cursor = await db.execute("SELECT id FROM categories WHERE name = ?", (name,))
        row = await cursor.fetchone()

        if row:
            return row[0]

        cursor = await db.execute(
            "INSERT INTO categories (name, source) VALUES (?, ?)", (name, source)
        )
        return cursor.lastrowid

    async def _row_to_paper(self, db: aiosqlite.Connection, row: aiosqlite.Row) -> Paper:
        """Convert database row to Paper model."""
        # Parse dates
        publication_date = datetime.fromisoformat(row["publication_date"])
        collected_at = datetime.fromisoformat(row["collected_at"])
        processed_at = (
            datetime.fromisoformat(row["processed_at"]) if row["processed_at"] else None
        )

        # Parse JSON fields
        key_ideas = json.loads(row["key_ideas"]) if row["key_ideas"] else None

        # Get authors
        cursor = await db.execute(
            """
            SELECT a.id, a.name, a.normalized_name
            FROM authors a
            JOIN paper_authors pa ON a.id = pa.author_id
            WHERE pa.paper_id = ?
            ORDER BY pa.author_order
            """,
            (row["id"],),
        )
        author_rows = await cursor.fetchall()
        authors = [
            Author(id=r["id"], name=r["name"], normalized_name=r["normalized_name"])
            for r in author_rows
        ]

        # Get categories
        cursor = await db.execute(
            """
            SELECT c.id, c.name, c.source
            FROM categories c
            JOIN paper_categories pc ON c.id = pc.category_id
            WHERE pc.paper_id = ?
            """,
            (row["id"],),
        )
        category_rows = await cursor.fetchall()
        categories = [
            Category(id=r["id"], name=r["name"], source=r["source"]) for r in category_rows
        ]

        return Paper(
            id=row["id"],
            arxiv_id=row["arxiv_id"],
            doi=row["doi"],
            url=row["url"],
            title=row["title"],
            abstract=row["abstract"],
            publication_date=publication_date,
            source=row["source"],
            collected_at=collected_at,
            processed_at=processed_at,
            ai_summary=row["ai_summary"],
            key_ideas=key_ideas,
            embedding=row["embedding"],
            authors=authors,
            categories=categories,
        )

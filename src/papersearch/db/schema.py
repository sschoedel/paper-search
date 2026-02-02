"""Database schema and initialization for papersearch."""

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# SQL schema definitions
SCHEMA_SQL = """
-- Main papers table
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arxiv_id TEXT UNIQUE,
    doi TEXT UNIQUE,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL,
    publication_date TEXT NOT NULL,
    source TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    processed_at TEXT,
    ai_summary TEXT,
    key_ideas TEXT,  -- JSON array
    embedding BLOB
);

CREATE INDEX IF NOT EXISTS idx_papers_date ON papers(publication_date);
CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source);
CREATE INDEX IF NOT EXISTS idx_papers_collected ON papers(collected_at);
CREATE INDEX IF NOT EXISTS idx_papers_processed ON papers(processed_at);

-- Authors table
CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_authors_normalized ON authors(normalized_name);

-- Many-to-many: papers <-> authors
CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    author_order INTEGER NOT NULL,
    PRIMARY KEY (paper_id, author_id),
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_paper_authors_paper ON paper_authors(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_authors_author ON paper_authors(author_id);

-- Categories table
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL
);

-- Many-to-many: papers <-> categories
CREATE TABLE IF NOT EXISTS paper_categories (
    paper_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    PRIMARY KEY (paper_id, category_id),
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_paper_categories_paper ON paper_categories(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_categories_category ON paper_categories(category_id);

-- Collection runs tracking
CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    papers_collected INTEGER DEFAULT 0,
    papers_processed INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_collection_runs_started ON collection_runs(started_at);

-- Duplicate tracking
CREATE TABLE IF NOT EXISTS duplicate_papers (
    canonical_paper_id INTEGER NOT NULL,
    duplicate_paper_id INTEGER NOT NULL,
    similarity_score REAL NOT NULL,
    PRIMARY KEY (canonical_paper_id, duplicate_paper_id),
    FOREIGN KEY (canonical_paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    FOREIGN KEY (duplicate_paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

-- Full-text search virtual table (FTS5)
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
    paper_id UNINDEXED,
    title,
    abstract,
    ai_summary,
    key_ideas,
    content=papers,
    content_rowid=id
);

-- Triggers to keep FTS table in sync
CREATE TRIGGER IF NOT EXISTS papers_fts_insert AFTER INSERT ON papers BEGIN
    INSERT INTO papers_fts(paper_id, title, abstract, ai_summary, key_ideas)
    VALUES (new.id, new.title, new.abstract, new.ai_summary, new.key_ideas);
END;

CREATE TRIGGER IF NOT EXISTS papers_fts_delete AFTER DELETE ON papers BEGIN
    DELETE FROM papers_fts WHERE paper_id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS papers_fts_update AFTER UPDATE ON papers BEGIN
    DELETE FROM papers_fts WHERE paper_id = old.id;
    INSERT INTO papers_fts(paper_id, title, abstract, ai_summary, key_ideas)
    VALUES (new.id, new.title, new.abstract, new.ai_summary, new.key_ideas);
END;
"""


async def initialize_database(db_path: Path) -> None:
    """Initialize database schema.

    Args:
        db_path: Path to SQLite database file
    """
    logger.info(f"Initializing database at {db_path}")

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        # Enable foreign keys
        await db.execute("PRAGMA foreign_keys = ON")

        # Execute schema
        await db.executescript(SCHEMA_SQL)
        await db.commit()

    logger.info("Database initialized successfully")


async def drop_database(db_path: Path) -> None:
    """Drop all tables (for testing).

    Args:
        db_path: Path to SQLite database file
    """
    logger.warning(f"Dropping all tables in {db_path}")

    async with aiosqlite.connect(db_path) as db:
        # Get all tables
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = await cursor.fetchall()

        # Drop each table
        for (table_name,) in tables:
            await db.execute(f"DROP TABLE IF EXISTS {table_name}")

        await db.commit()

    logger.info("All tables dropped")

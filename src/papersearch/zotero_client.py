"""Zotero API client for paper storage."""

import logging
from typing import Optional

from pyzotero import zotero

from .config import Settings
from .db.models import Paper

logger = logging.getLogger(__name__)


class ZoteroClient:
    """Client for interacting with Zotero API."""

    def __init__(self, settings: Settings):
        """Initialize Zotero client.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.zot = zotero.Zotero(
            settings.zotero_library_id,
            settings.zotero_library_type,
            settings.zotero_api_key,
        )

    def add_paper(self, paper: Paper) -> str:
        """Add paper to Zotero library.

        Args:
            paper: Paper to add

        Returns:
            Zotero item key
        """
        # Create Zotero item template
        if paper.arxiv_id:
            # Use preprint template for arXiv papers
            item_type = "preprint"
        else:
            item_type = "journalArticle"

        template = self.zot.item_template(item_type)

        # Fill in metadata
        template["title"] = paper.title
        template["abstractNote"] = paper.abstract
        template["url"] = paper.url
        template["date"] = paper.publication_date.strftime("%Y-%m-%d")

        # Add arXiv ID to extra field
        if paper.arxiv_id:
            template["extra"] = f"arXiv: {paper.arxiv_id}"

        if paper.doi:
            template["DOI"] = paper.doi

        # Add authors
        template["creators"] = [
            {"creatorType": "author", "firstName": "", "lastName": author.name}
            for author in paper.authors
        ]

        # Add tags from categories
        template["tags"] = [{"tag": cat.name} for cat in paper.categories]

        # Add source tag
        template["tags"].append({"tag": f"source:{paper.source}"})

        # Create the item
        resp = self.zot.create_items([template])

        if not resp["successful"]:
            raise RuntimeError(f"Failed to create Zotero item: {resp}")

        item_key = resp["successful"]["0"]["key"]
        logger.info(f"Created Zotero item: {item_key} - {paper.title[:60]}")

        # Add AI summary and key ideas as a note
        if paper.ai_summary or paper.key_ideas:
            self._add_summary_note(item_key, paper)

        return item_key

    def _add_summary_note(self, parent_key: str, paper: Paper) -> None:
        """Add AI-generated summary as a note.

        Args:
            parent_key: Parent item key
            paper: Paper with summary/key ideas
        """
        note_content = "<h2>AI Summary</h2>\n"

        if paper.ai_summary:
            note_content += f"<p>{paper.ai_summary}</p>\n"

        if paper.key_ideas:
            note_content += "<h3>Key Ideas</h3>\n<ul>\n"
            for idea in paper.key_ideas:
                note_content += f"<li>{idea}</li>\n"
            note_content += "</ul>\n"

        # Create note
        note_template = self.zot.item_template("note")
        note_template["note"] = note_content
        note_template["parentItem"] = parent_key

        resp = self.zot.create_items([note_template])

        if not resp["successful"]:
            logger.error(f"Failed to create note for {parent_key}: {resp}")
        else:
            logger.debug(f"Added summary note to {parent_key}")

    def find_duplicate(self, paper: Paper) -> Optional[str]:
        """Check if paper already exists in library.

        Args:
            paper: Paper to check

        Returns:
            Zotero item key if duplicate found, None otherwise
        """
        # Search by arXiv ID if available
        if paper.arxiv_id:
            results = self.zot.everything(
                self.zot.items(q=paper.arxiv_id, qmode="everything")
            )
            if results:
                logger.debug(f"Found duplicate by arXiv ID: {paper.arxiv_id}")
                return results[0]["key"]

        # Search by DOI if available
        if paper.doi:
            results = self.zot.everything(self.zot.items(q=paper.doi, qmode="everything"))
            if results:
                logger.debug(f"Found duplicate by DOI: {paper.doi}")
                return results[0]["key"]

        # Search by title (fuzzy)
        results = self.zot.everything(self.zot.items(q=paper.title, qmode="titleCreatorYear"))
        if results:
            # Check if any result has similar title
            from thefuzz import fuzz

            for item in results:
                if "data" in item and "title" in item["data"]:
                    similarity = fuzz.ratio(
                        paper.title.lower(), item["data"]["title"].lower()
                    )
                    if similarity > 95:
                        logger.debug(f"Found duplicate by title: {item['data']['title']}")
                        return item["key"]

        return None

    def update_paper_summary(self, item_key: str, paper: Paper) -> None:
        """Update paper with AI summary.

        Args:
            item_key: Zotero item key
            paper: Paper with updated summary
        """
        # Get existing notes
        notes = self.zot.children(item_key, itemType="note")

        # Check if summary note exists
        summary_note = None
        for note in notes:
            if "AI Summary" in note["data"].get("note", ""):
                summary_note = note
                break

        if summary_note:
            # Update existing note
            note_content = "<h2>AI Summary</h2>\n"
            if paper.ai_summary:
                note_content += f"<p>{paper.ai_summary}</p>\n"
            if paper.key_ideas:
                note_content += "<h3>Key Ideas</h3>\n<ul>\n"
                for idea in paper.key_ideas:
                    note_content += f"<li>{idea}</li>\n"
                note_content += "</ul>\n"

            summary_note["data"]["note"] = note_content
            self.zot.update_item(summary_note)
            logger.debug(f"Updated summary note for {item_key}")
        else:
            # Create new note
            self._add_summary_note(item_key, paper)

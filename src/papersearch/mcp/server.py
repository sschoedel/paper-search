"""MCP server for papersearch."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from ..config import get_settings
from ..db.repository import PaperRepository

logger = logging.getLogger(__name__)

# Initialize server
app = Server("papersearch")

# Global repository instance
repository: Optional[PaperRepository] = None


def get_repository() -> PaperRepository:
    """Get or create repository instance."""
    global repository
    if repository is None:
        settings = get_settings()
        repository = PaperRepository(settings.database_path)
    return repository


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="search_papers",
            description="Full-text search across papers (title, abstract, summary, key ideas)",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Filter by publication date from (YYYY-MM-DD)",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Filter by publication date to (YYYY-MM-DD)",
                    },
                    "source": {
                        "type": "string",
                        "description": "Filter by source (e.g., 'arxiv', 'rss:BAIR')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_paper_details",
            description="Get complete details for a specific paper by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID",
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="list_recent_papers",
            description="List recent papers chronologically",
            inputSchema={
                "type": "object",
                "properties": {
                    "timeframe": {
                        "type": "string",
                        "description": "Time period: 'today', 'week', or 'month'",
                        "enum": ["today", "week", "month"],
                        "default": "today",
                    },
                    "source": {
                        "type": "string",
                        "description": "Filter by source (e.g., 'arxiv', 'rss:BAIR')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20)",
                        "default": 20,
                    },
                },
            },
        ),
        Tool(
            name="find_related_papers",
            description="Find semantically similar papers using embeddings",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Reference paper ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 5)",
                        "default": 5,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="get_daily_summary",
            description="Get daily digest of collected papers",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format (defaults to today)",
                    },
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    try:
        repo = get_repository()

        if name == "search_papers":
            return await handle_search_papers(repo, arguments)
        elif name == "get_paper_details":
            return await handle_get_paper_details(repo, arguments)
        elif name == "list_recent_papers":
            return await handle_list_recent_papers(repo, arguments)
        elif name == "find_related_papers":
            return await handle_find_related_papers(repo, arguments)
        elif name == "get_daily_summary":
            return await handle_get_daily_summary(repo, arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Error in tool {name}: {e}", exc_info=True)
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_search_papers(repo: PaperRepository, args: dict) -> list[TextContent]:
    """Handle search_papers tool."""
    query = args["query"]
    date_from = args.get("date_from")
    date_to = args.get("date_to")
    source = args.get("source")
    limit = args.get("limit", 10)

    # Parse dates
    date_from_dt = datetime.fromisoformat(date_from) if date_from else None
    date_to_dt = datetime.fromisoformat(date_to) if date_to else None

    results = await repo.search_papers(query, date_from_dt, date_to_dt, source, limit)

    if not results:
        return [TextContent(type="text", text=f"No papers found matching: {query}")]

    # Format results
    text = f"Found {len(results)} papers matching '{query}':\n\n"

    for i, result in enumerate(results, 1):
        paper = result.paper
        text += f"{i}. **{paper.title}** (ID: {paper.id})\n"
        text += f"   Authors: {', '.join(a.name for a in paper.authors[:3])}"
        if len(paper.authors) > 3:
            text += f" et al."
        text += f"\n"
        text += f"   Date: {paper.publication_date.strftime('%Y-%m-%d')}\n"
        text += f"   Source: {paper.source}\n"

        if paper.ai_summary:
            text += f"   Summary: {paper.ai_summary}\n"

        text += f"   URL: {paper.url}\n\n"

    return [TextContent(type="text", text=text)]


async def handle_get_paper_details(repo: PaperRepository, args: dict) -> list[TextContent]:
    """Handle get_paper_details tool."""
    paper_id = args["paper_id"]
    paper = await repo.get_paper(paper_id)

    if not paper:
        return [TextContent(type="text", text=f"Paper {paper_id} not found")]

    # Format paper details
    text = f"# {paper.title}\n\n"

    text += f"**Paper ID:** {paper.id}\n"
    if paper.arxiv_id:
        text += f"**arXiv ID:** {paper.arxiv_id}\n"
    if paper.doi:
        text += f"**DOI:** {paper.doi}\n"

    text += f"**Published:** {paper.publication_date.strftime('%Y-%m-%d')}\n"
    text += f"**Source:** {paper.source}\n"
    text += f"**URL:** {paper.url}\n\n"

    if paper.authors:
        text += f"**Authors:** {', '.join(a.name for a in paper.authors)}\n\n"

    if paper.categories:
        text += f"**Categories:** {', '.join(c.name for c in paper.categories)}\n\n"

    text += f"## Abstract\n\n{paper.abstract}\n\n"

    if paper.ai_summary:
        text += f"## AI Summary\n\n{paper.ai_summary}\n\n"

    if paper.key_ideas:
        text += f"## Key Ideas\n\n"
        for idea in paper.key_ideas:
            text += f"- {idea}\n"
        text += "\n"

    return [TextContent(type="text", text=text)]


async def handle_list_recent_papers(repo: PaperRepository, args: dict) -> list[TextContent]:
    """Handle list_recent_papers tool."""
    timeframe = args.get("timeframe", "today")
    source = args.get("source")
    limit = args.get("limit", 20)

    # Convert timeframe to days
    days_map = {"today": 1, "week": 7, "month": 30}
    days = days_map.get(timeframe, 1)

    papers = await repo.list_recent_papers(days, source, limit)

    if not papers:
        return [TextContent(type="text", text=f"No papers found in the last {timeframe}")]

    # Format results
    text = f"Recent papers ({timeframe}):\n\n"

    for i, paper in enumerate(papers, 1):
        text += f"{i}. **{paper.title}** (ID: {paper.id})\n"
        text += f"   Authors: {', '.join(a.name for a in paper.authors[:3])}"
        if len(paper.authors) > 3:
            text += f" et al."
        text += f"\n"
        text += f"   Date: {paper.publication_date.strftime('%Y-%m-%d')}\n"
        text += f"   Source: {paper.source}\n"

        if paper.ai_summary:
            summary_preview = paper.ai_summary[:150]
            if len(paper.ai_summary) > 150:
                summary_preview += "..."
            text += f"   Summary: {summary_preview}\n"

        text += f"   URL: {paper.url}\n\n"

    return [TextContent(type="text", text=text)]


async def handle_find_related_papers(repo: PaperRepository, args: dict) -> list[TextContent]:
    """Handle find_related_papers tool."""
    paper_id = args["paper_id"]
    limit = args.get("limit", 5)

    # Get reference paper
    ref_paper = await repo.get_paper(paper_id)
    if not ref_paper:
        return [TextContent(type="text", text=f"Paper {paper_id} not found")]

    # Find related papers
    results = await repo.find_related_papers(paper_id, limit)

    if not results:
        return [
            TextContent(
                type="text",
                text=f"No related papers found for: {ref_paper.title}\n\n"
                + "(This paper may not have embeddings generated yet)",
            )
        ]

    # Format results
    text = f"Papers related to: **{ref_paper.title}**\n\n"

    for i, result in enumerate(results, 1):
        paper = result.paper
        similarity = result.score * 100 if result.score else 0

        text += f"{i}. **{paper.title}** (ID: {paper.id})\n"
        text += f"   Similarity: {similarity:.1f}%\n"
        text += f"   Authors: {', '.join(a.name for a in paper.authors[:3])}"
        if len(paper.authors) > 3:
            text += f" et al."
        text += f"\n"
        text += f"   Date: {paper.publication_date.strftime('%Y-%m-%d')}\n"

        if paper.ai_summary:
            summary_preview = paper.ai_summary[:150]
            if len(paper.ai_summary) > 150:
                summary_preview += "..."
            text += f"   Summary: {summary_preview}\n"

        text += f"   URL: {paper.url}\n\n"

    return [TextContent(type="text", text=text)]


async def handle_get_daily_summary(repo: PaperRepository, args: dict) -> list[TextContent]:
    """Handle get_daily_summary tool."""
    date_str = args.get("date")
    date = datetime.fromisoformat(date_str) if date_str else datetime.now(timezone.utc)

    summary = await repo.get_daily_summary(date)

    if summary.total_papers == 0:
        return [
            TextContent(
                type="text",
                text=f"No papers collected on {summary.date}",
            )
        ]

    # Format summary
    text = f"# Daily Summary for {summary.date}\n\n"
    text += f"**Total Papers:** {summary.total_papers}\n\n"

    if summary.papers_by_source:
        text += "## Papers by Source\n\n"
        for source, count in summary.papers_by_source.items():
            text += f"- {source}: {count}\n"
        text += "\n"

    if summary.top_categories:
        text += "## Top Categories\n\n"
        for category, count in summary.top_categories:
            text += f"- {category}: {count}\n"
        text += "\n"

    if summary.highlights:
        text += "## Highlights\n\n"
        for paper in summary.highlights:
            text += f"### {paper.title} (ID: {paper.id})\n\n"
            if paper.ai_summary:
                text += f"{paper.ai_summary}\n\n"
            text += f"[Read more]({paper.url})\n\n"

    return [TextContent(type="text", text=text)]


async def main():
    """Run MCP server."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting papersearch MCP server")

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

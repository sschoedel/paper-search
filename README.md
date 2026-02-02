# Paper Search System

A paper aggregation system that collects RL/robotics papers daily from arXiv and RSS feeds, summarizes them with LLMs, and stores them in your Zotero library for easy access via the Zotero MCP server in Claude Code.

## Features

- **Automated Collection**: Daily collection from arXiv and RSS feeds
- **Smart Deduplication**: Checks against your existing Zotero library
- **LLM Summaries**: Configurable summarization with Claude or OpenAI
- **Zotero Integration**: Stores papers directly in your Zotero library
- **MCP Access**: Use existing Zotero MCP server to search/browse in Claude Code

## Quick Start

1. Get Zotero API credentials from https://www.zotero.org/settings/keys
2. Install dependencies: `uv venv && source .venv/bin/activate && uv pip install -e .`
3. Configure: `cp .env.example .env` and add your API keys
4. Install Zotero MCP server (see Setup section below)
5. Test: `python scripts/run_collection.py --dry-run`

## Architecture

```
Daily Pipeline:
1. Collect papers from arXiv + RSS
2. Deduplicate against Zotero library
3. Generate AI summaries + key ideas
4. Store in Zotero with summaries as notes

Claude Code Integration:
- Use existing Zotero MCP server
- Search papers, read summaries, browse library
```

## Setup

### 1. Get Zotero API Credentials

1. Go to https://www.zotero.org/settings/keys
2. Create a new API key with read/write permissions
3. Note your User ID (shown on the settings page)

### 2. Install Dependencies

```bash
uv venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows
uv pip install -e .
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials:
# - Zotero API key and library ID
# - Anthropic or OpenAI API key for summaries
```

### 4. Install Zotero MCP Server

Follow the instructions at: https://github.com/zotero/zotero-mcp-server

Add to your `~/.config/claude-code/mcp.json`:

```json
{
  "mcpServers": {
    "zotero": {
      "command": "npx",
      "args": ["-y", "@zotero/mcp-server"]
    }
  }
}
```

**Important:** Restart Claude Code after adding the MCP server configuration.

### 5. Test Collection

```bash
python scripts/run_collection.py --dry-run
```

## Daily Automation

### macOS (cron):
```bash
crontab -e
# Add: 0 9 * * * /path/to/.venv/bin/python /path/to/scripts/run_collection.py
```

### Linux (systemd):
```bash
sudo cp config/systemd/papersearch.service /etc/systemd/system/
sudo cp config/systemd/papersearch.timer /etc/systemd/system/
sudo systemctl enable papersearch.timer
sudo systemctl start papersearch.timer
```

## Usage with Claude Code

Once papers are in your Zotero library, use the Zotero MCP server in Claude Code:

- "Show me recent papers in my Zotero library"
- "Search for papers about robot learning"
- "What are the key ideas from [paper title]?"

The AI summaries and key ideas are stored as notes attached to each paper.

## Configuration

### Collection Sources

Edit `config/queries.yaml` for arXiv search queries:
```yaml
arxiv:
  categories: [cs.LG, cs.RO, cs.AI]
  keywords:
    - "reinforcement learning"
    - "robot learning"
    # ...
```

Edit `config/rss_feeds.yaml` for RSS feeds:
```yaml
feeds:
  - url: "https://bair.berkeley.edu/blog/feed.xml"
    name: "BAIR"
  # ...
```

### LLM Configuration

Choose your summarization model in `.env`:
- Claude: `SUMMARIZATION_MODEL=claude-3-haiku-20240307` (requires paid credits)
- OpenAI: `SUMMARIZATION_MODEL=gpt-4o-mini` (may have free trial credits)
- No summaries: `SUMMARIZATION_ENABLED=false` (free - just collect papers)

## Future Enhancements

- **Phase 2**: Add semantic search with embeddings
  - Small SQLite DB for embeddings
  - Custom MCP tool: `find_similar_papers(zotero_item_id)`
  - Discover related papers by concept, not just keywords

## Troubleshooting

### "ZOTERO_LIBRARY_ID required"
- Make sure you've copied `.env.example` to `.env`
- Add your Zotero credentials from https://www.zotero.org/settings/keys

### "ANTHROPIC_API_KEY required"
- Add your Anthropic API key to `.env`
- Or use OpenAI by setting `OPENAI_API_KEY` and `SUMMARIZATION_MODEL=gpt-4o-mini`

### "No papers found"
- Adjust `LOOKBACK_HOURS` in `.env` (default is 24 hours)
- Check that arXiv and RSS feeds are accessible
- Try a dry run with `--log-level DEBUG` for more details

### Zotero MCP not showing in Claude Code
- Verify the MCP configuration in `~/.config/claude-code/mcp.json`
- Restart Claude Code completely
- Check that `npx` is available in your PATH

## License

MIT

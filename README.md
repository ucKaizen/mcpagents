# AGF Media Measurement — MCP Agent Demo

A realistic proof-of-concept demonstrating **Model Context Protocol (MCP)** with an LLM agent. The system simulates [AGF Germany](https://www.agf.de/)-style TV audience measurement data — reach, market share, cross-media metrics — all queryable by program, channel, genre, and demographic breakdowns (age group + gender).

A web interface lets you chat with the LLM and watch MCP tool calls happen in real time.

![Architecture](#architecture)

## Architecture

```
┌──────────────┐     WebSocket      ┌──────────────────┐      MCP/HTTP       ┌─────────────────┐
│  Browser UI  │◄──────────────────►│  Agent Bridge     │◄──────────────────►│  MCP Server      │
│  (chat +     │   assistant text   │  (FastAPI +       │   tool discovery   │  (FastMCP)       │
│   tool       │   + tool events    │   OpenAI LLM)     │   + tool calls     │  9 media tools   │
│   inspector) │                    │  :8001            │                    │  :8000/mcp       │
└──────────────┘                    └──────────────────┘                    └─────────────────┘
```

**Flow:** User asks a question in the browser. The agent discovers available MCP tools, sends the question + tool definitions to OpenAI, the LLM decides which tools to call, the agent executes them against the MCP server, and streams results back to the browser — including a live inspector showing every tool call and response.

## Features

- **9 MCP tools** for media measurement analytics
- **Realistic data** — deterministic generation calibrated to real German TV audience ranges
- **Demographic resolution** — 5 age groups (3-13, 14-29, 30-49, 50-64, 65+) x 2 genders
- **Cross-media** — TV + streaming reach with age-dependent streaming skew
- **Web UI** — chat panel + live MCP tool inspector
- **CLI mode** — also works as a terminal chatbot

## MCP Tools

| Tool | Description |
|------|-------------|
| `list_channels()` | List all 10 German TV channels with metadata |
| `list_programs(channel?, genre?)` | Browse programs, filter by channel or genre |
| `get_program_reach(program, age_group?, gender?)` | Reach (thousands + %) for a program |
| `get_channel_share(channel, age_group?, gender?)` | Market share % for a channel |
| `get_genre_performance(genre, age_group?, gender?)` | Aggregated metrics for a genre |
| `get_top_programs(metric?, n?, age_group?, gender?)` | Top N programs by reach or share |
| `get_demographic_breakdown(name, entity_type?)` | Full age x gender matrix |
| `get_cross_media_reach(name, entity_type?, age_group?, gender?)` | TV + streaming + total reach |
| `compare_channels(channels, metric?, age_group?, gender?)` | Side-by-side channel comparison |

## Quickstart

### Prerequisites

- Python 3.10+
- An OpenAI API key

### Setup

```bash
# Clone and create virtual environment
git clone <repo-url>
cd mcpagents
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

Your `.env` file should contain:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini     # optional, defaults to gpt-4o-mini
MCP_URL=http://127.0.0.1:8000/mcp
```

### Run (Web UI)

Open two terminals:

**Terminal 1 — Start the MCP server:**

```bash
./start_server.sh
# Or directly:
cd server && python3 app_mcp.py
```

The MCP server starts on `http://127.0.0.1:8000/mcp`.

**Terminal 2 — Start the web agent:**

```bash
./start_agent.sh
# Or directly:
python3 agent/dynamic_gpt_mcp_bridge.py
```

The web UI opens on `http://localhost:8001`. Open it in your browser.

### Run (CLI mode)

If you prefer a terminal-based chat:

```bash
./start_agent.sh --cli
```

## Example Queries

Try these in the chat:

- *"What are the top 5 programs by reach among viewers aged 14-29?"*
- *"Compare Das Erste, ZDF, and RTL market share for female viewers"*
- *"Show me the full demographic breakdown for Tatort"*
- *"What is the cross-media reach of Germanys Next Topmodel among 14-29 year olds?"*
- *"Which genre performs best among male viewers aged 30-49?"*
- *"List all programs on ZDF"*
- *"What is the market share of ProSieben among 14-29 year old females?"*

The LLM will chain multiple tool calls when needed — for example, first listing programs to discover names, then querying detailed metrics.

## Project Structure

```
mcpagents/
├── server/
│   ├── app_mcp.py          # FastMCP server — 9 media measurement tools
│   └── media_data.py       # Reference data + deterministic data engine
├── agent/
│   └── dynamic_gpt_mcp_bridge.py  # FastAPI web server + WebSocket + OpenAI bridge
├── web/
│   └── index.html          # Single-page chat UI + tool inspector
├── slm/                    # Separate NER service (unrelated to MCP demo)
├── requirements.txt
├── start_server.sh
├── start_agent.sh
└── README.md
```

## Data Design

No database or static files. All audience data is generated **deterministically** from hash-based seeds combined with realistic demographic bias matrices:

- **Genre biases** — News skews 65+ (1.9x), Entertainment skews 14-29 (1.5x), Sports skews Male (1.45x)
- **Channel biases** — ARD/ZDF dominate older demographics, ProSieben strongest with 14-29
- **Calibrated ranges** — Tagesschau ~9M reach, ARD ~12% share, ZDF ~13% share, matching real AGF data
- **Cross-media** — Streaming adds 5-25% on top of linear TV, with heavy skew toward younger demographics
- **Deterministic** — Same query always returns the same numbers (seeded via MD5 hash)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| MCP Server | [FastMCP](https://github.com/jlowin/fastmcp) (Python) |
| LLM | OpenAI API (gpt-4o-mini default) |
| Web Agent | FastAPI + WebSocket |
| Web UI | Vanilla HTML/CSS/JS (no build step) |
| Data | Deterministic generation, no database |

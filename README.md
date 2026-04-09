# AGF Media Measurement — MCP Agent Demo

A proof-of-concept demonstrating **dynamic tool discovery** with MCP and LLMs. The system simulates [AGF Germany](https://www.agf.de/)-style TV audience measurement data — reach, market share, cross-media metrics — all queryable by program, channel, genre, and demographic breakdowns.

**Key demo:** Toolsets register/deregister at runtime. The LLM discovers new capabilities on each turn — start with basic metrics, then bring advanced analytics online and watch the LLM immediately use them.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Railway Project                                     │
│                                                                              │
│  Service 1: Gateway (:8000)                                                  │
│  ┌──────────────────────────────┐         Service 2: Basic Metrics (:8002)  │
│  │  Tool Registry (REST API)    │◄─register──┌──────────────────────┐       │
│  │  Web Agent (OpenAI LLM)      │──invoke───►│ list_channels        │       │
│  │  Web UI (chat + inspector)   │            │ list_programs         │       │
│  │                              │            │ get_program_reach     │       │
│  │  /api/register               │            │ get_channel_share     │       │
│  │  /api/deregister/{name}      │            └──────────────────────┘       │
│  │  /api/toolsets               │                                            │
│  │  /ws/chat                    │         Service 3: Advanced Analytics      │
│  │                              │◄─register──┌──────────────────────┐       │
│  │                              │──invoke───►│ get_top_programs      │       │
│  └──────────────────────────────┘            │ get_demographic_brkdn │       │
│                                              │ get_cross_media_reach │       │
│   Browser ◄──WebSocket──► Gateway            │ compare_channels      │       │
│                                              │ get_genre_performance │       │
│                                              └──────────────────────┘       │
└──────────────────────────────────────────────────────────────────────────────┘
```

**How it works:**
1. Gateway starts — no tools available yet
2. Toolset services start and POST their tool definitions to `POST /api/register`
3. On each chat message, the gateway discovers currently registered tools
4. The LLM decides which tools to call; gateway proxies calls to the owning toolset
5. If a toolset stops, its tools disappear — the LLM adapts on the next turn

## Demo Flow

1. Start the gateway — chat says "No tools available"
2. Start Basic Metrics — UI shows the toolset come online with 4 tools
3. Ask: *"What is the reach of Tagesschau among 65+?"* — LLM uses `get_program_reach`
4. Ask: *"Show me the full demographic breakdown for Tatort"* — LLM says it can't (no tool for that)
5. Start Advanced Analytics — UI shows 5 more tools come online
6. Ask the same question — LLM now uses `get_demographic_breakdown` and gives a full matrix
7. Stop Basic Metrics — LLM loses foundational tools but retains advanced ones

## Tools

### Toolset: Basic Metrics
| Tool | Description |
|------|-------------|
| `list_channels()` | List all 10 German TV channels |
| `list_programs(channel?, genre?)` | Browse programs with filters |
| `get_program_reach(program, age_group?, gender?)` | Reach in thousands + % |
| `get_channel_share(channel, age_group?, gender?)` | Market share % |

### Toolset: Advanced Analytics
| Tool | Description |
|------|-------------|
| `get_top_programs(metric?, n?, age_group?, gender?)` | Top N programs ranked |
| `get_demographic_breakdown(name, entity_type?)` | Full age x gender matrix |
| `get_cross_media_reach(name, entity_type?, age_group?, gender?)` | TV + streaming reach |
| `compare_channels(channels, metric?, age_group?, gender?)` | Side-by-side comparison |
| `get_genre_performance(genre, age_group?, gender?)` | Aggregated genre metrics |

## Quickstart (Local)

### Prerequisites
- Python 3.10+
- OpenAI API key

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
```

### Run (3 terminals)

**Terminal 1 — Gateway:**
```bash
python3 gateway/app.py
# Starts on http://localhost:8000
```

**Terminal 2 — Basic Metrics toolset:**
```bash
python3 toolsets/basic_metrics.py
# Registers 4 tools with the gateway
```

**Terminal 3 — Advanced Analytics toolset:**
```bash
python3 toolsets/advanced_analytics.py
# Registers 5 tools with the gateway
```

Open **http://localhost:8000** in your browser.

Start/stop toolsets at any time — the UI updates in real time and the LLM adapts on the next message.

## Deploy to Railway

### 1. Create 3 services from the same repo

In Railway, create a new project, then add 3 services all pointing to the `ucKaizen/mcpagents` GitHub repo:

| Service | Dockerfile | Environment Variables |
|---------|------------|----------------------|
| **gateway** | `gateway/Dockerfile` | `OPENAI_API_KEY=sk-...` |
| **basic-metrics** | `toolsets/Dockerfile.basic` | `GATEWAY_URL=http://gateway.railway.internal:8000`, `SELF_URL=http://basic-metrics.railway.internal:8002` |
| **advanced-analytics** | `toolsets/Dockerfile.advanced` | `GATEWAY_URL=http://gateway.railway.internal:8000`, `SELF_URL=http://advanced-analytics.railway.internal:8003` |

### 2. Configure networking

- Generate a **public domain** for the gateway service only (this is the URL you open in browser)
- Toolsets communicate with the gateway via Railway's **internal networking** (`.railway.internal`)

### 3. Demo

- Stop/start the toolset services from the Railway dashboard
- Watch the chat UI react in real time

## Project Structure

```
mcpagents/
├── gateway/
│   ├── app.py              # Gateway: registry + web agent + UI server
│   └── Dockerfile
├── toolsets/
│   ├── basic_metrics.py    # Toolset 1: list, reach, share
│   ├── advanced_analytics.py # Toolset 2: top, demographics, cross-media
│   ├── Dockerfile.basic
│   └── Dockerfile.advanced
├── server/
│   └── media_data.py       # Shared data engine (deterministic, no DB)
├── web/
│   └── index.html          # Chat UI + tool inspector + toolset status
├── requirements.txt
└── README.md
```

## Data Design

No database. All audience data is generated deterministically from hash-based seeds + realistic demographic bias matrices:

- **Genre biases** — News skews 65+ (1.9x), Entertainment skews 14-29 (1.5x), Sports skews Male (1.45x)
- **Channel biases** — ARD/ZDF dominate older demographics, ProSieben strongest with 14-29
- **Calibrated** — Tagesschau ~9M reach, ARD ~12% share, matching real AGF data
- **Cross-media** — Streaming adds 5-25% on top of linear TV, heavier for younger viewers
- **Deterministic** — Same query always returns the same numbers

## Chatbot Constraints

The LLM is configured as a **specialized media analytics assistant**. It will:
- Only answer questions about German TV audience measurement
- Only use data from registered tools (never guess or make up numbers)
- Clearly state when a capability is missing (toolset not registered)
- Decline unrelated questions (coding, general knowledge, etc.)

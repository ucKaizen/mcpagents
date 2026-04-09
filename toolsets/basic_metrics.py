"""
Toolset: Basic Metrics

Self-registering service that provides foundational TV measurement tools:
  - list_channels
  - list_programs
  - get_program_reach
  - get_channel_share

On startup, registers with the gateway. On shutdown, deregisters.
"""

import os, sys, signal, pathlib, asyncio
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import uvicorn

# Add server/ to path for media_data imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "server"))

from media_data import (
    CHANNELS, PROGRAMS, GENRES, AGE_GROUPS, GENDERS,
    compute_reach, compute_share,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8000")
PORT = int(os.getenv("PORT", "8002"))
SELF_URL = os.getenv("SELF_URL", f"http://127.0.0.1:{PORT}")
TOOLSET_NAME = "basic-metrics"

# ---------------------------------------------------------------------------
# Tool definitions (schema for registration with gateway)
# ---------------------------------------------------------------------------
TOOL_DEFS = [
    {
        "name": "list_channels",
        "description": (
            "List all available German TV channels. "
            "Returns channels with name, type (public/private), group, and description. "
            "Use this tool first to discover available channel names before querying metrics."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_programs",
        "description": (
            "List TV programs, optionally filtered by channel and/or genre. "
            "Returns programs with channel, genre, timeslot, day, and duration. "
            "Use this to discover program names before querying detailed metrics.\n\n"
            "Args:\n"
            "  channel: Filter by channel name (e.g. 'Das Erste', 'RTL', 'ZDF'). Optional.\n"
            "  genre: Filter by genre (News, Crime, Entertainment, Sports, Soap, "
            "Documentary, Talk, Reality, Film). Optional."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Filter by channel name"},
                "genre": {"type": "string", "description": "Filter by genre name"},
            },
        },
    },
    {
        "name": "get_program_reach",
        "description": (
            "Get audience reach for a specific TV program. "
            "Returns reach in thousands, reach percentage, and average viewing minutes.\n\n"
            "Args:\n"
            "  program: Exact program name (e.g. 'Tatort', 'Tagesschau', 'GZSZ'). Use list_programs() to find valid names.\n"
            "  age_group: Optional demographic filter. One of: '3-13', '14-29', '30-49', '50-64', '65+'\n"
            "  gender: Optional demographic filter. One of: 'Male', 'Female'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "program": {"type": "string", "description": "Exact program name"},
                "age_group": {"type": "string", "description": "Age group filter: 3-13, 14-29, 30-49, 50-64, 65+"},
                "gender": {"type": "string", "description": "Gender filter: Male or Female"},
            },
            "required": ["program"],
        },
    },
    {
        "name": "get_channel_share",
        "description": (
            "Get market share percentage for a TV channel. "
            "Market share = percentage of all viewers watching TV who were tuned to this channel.\n\n"
            "Args:\n"
            "  channel: Channel name (e.g. 'Das Erste', 'ZDF', 'RTL', 'ProSieben'). Use list_channels() to find valid names.\n"
            "  age_group: Optional demographic filter. One of: '3-13', '14-29', '30-49', '50-64', '65+'\n"
            "  gender: Optional demographic filter. One of: 'Male', 'Female'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name"},
                "age_group": {"type": "string", "description": "Age group filter"},
                "gender": {"type": "string", "description": "Gender filter: Male or Female"},
            },
            "required": ["channel"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def handle_list_channels(args: dict) -> dict:
    result = []
    for name, info in CHANNELS.items():
        result.append({
            "name": name,
            "type": info["type"],
            "group": info["group"],
            "description": info["description"],
        })
    return {"channels": result, "count": len(result)}


def handle_list_programs(args: dict) -> dict:
    channel = args.get("channel")
    genre = args.get("genre")
    result = []
    for name, info in PROGRAMS.items():
        if channel and info["channel"] != channel:
            continue
        if genre and info["genre"] != genre:
            continue
        result.append({
            "name": name,
            "channel": info["channel"],
            "genre": info["genre"],
            "timeslot": info["timeslot"],
            "day": info["day"],
            "duration_minutes": info["duration_min"],
        })
    if not result:
        return {
            "error": f"No programs found with the given filters",
            "available_channels": list(CHANNELS.keys()),
            "available_genres": GENRES,
        }
    return {"programs": result, "count": len(result)}


def handle_get_program_reach(args: dict) -> dict:
    program = args.get("program", "")
    age_group = args.get("age_group")
    gender = args.get("gender")
    if age_group and age_group not in AGE_GROUPS:
        return {"error": f"Invalid age_group '{age_group}'. Valid: {AGE_GROUPS}"}
    if gender and gender not in GENDERS:
        return {"error": f"Invalid gender '{gender}'. Valid: {GENDERS}"}
    return compute_reach(program, age_group, gender)


def handle_get_channel_share(args: dict) -> dict:
    channel = args.get("channel", "")
    age_group = args.get("age_group")
    gender = args.get("gender")
    if age_group and age_group not in AGE_GROUPS:
        return {"error": f"Invalid age_group '{age_group}'. Valid: {AGE_GROUPS}"}
    if gender and gender not in GENDERS:
        return {"error": f"Invalid gender '{gender}'. Valid: {GENDERS}"}
    return compute_share(channel, "channel", age_group, gender)


TOOL_HANDLERS = {
    "list_channels": handle_list_channels,
    "list_programs": handle_list_programs,
    "get_program_reach": handle_get_program_reach,
    "get_channel_share": handle_get_channel_share,
}


# ---------------------------------------------------------------------------
# Registration with gateway
# ---------------------------------------------------------------------------
async def register_with_gateway():
    """Register this toolset with the gateway."""
    payload = {
        "toolset_name": TOOLSET_NAME,
        "callback_url": f"{SELF_URL}/invoke",
        "tools": TOOL_DEFS,
    }
    for attempt in range(10):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{GATEWAY_URL}/api/register", json=payload)
                resp.raise_for_status()
                print(f"[{TOOLSET_NAME}] Registered with gateway: {resp.json()}")
                return
        except Exception as e:
            print(f"[{TOOLSET_NAME}] Registration attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2)
    print(f"[{TOOLSET_NAME}] WARNING: Could not register with gateway after 10 attempts")


async def deregister_from_gateway():
    """Deregister this toolset from the gateway."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{GATEWAY_URL}/api/deregister/{TOOLSET_NAME}")
            print(f"[{TOOLSET_NAME}] Deregistered from gateway: {resp.json()}")
    except Exception as e:
        print(f"[{TOOLSET_NAME}] Deregistration failed: {e}")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await register_with_gateway()
    yield
    await deregister_from_gateway()

app = FastAPI(title=f"Toolset: {TOOLSET_NAME}", lifespan=lifespan)


class InvokeRequest(BaseModel):
    tool_name: str
    arguments: dict = {}


@app.post("/invoke")
async def invoke_tool(req: InvokeRequest):
    handler = TOOL_HANDLERS.get(req.tool_name)
    if not handler:
        return {"error": f"Tool '{req.tool_name}' not found in {TOOLSET_NAME}"}
    try:
        return handler(req.arguments)
    except Exception as e:
        return {"error": str(e)}


@app.get("/health")
async def health():
    return {"ok": True, "toolset": TOOLSET_NAME, "tools": list(TOOL_HANDLERS.keys())}


if __name__ == "__main__":
    print(f"Starting {TOOLSET_NAME} toolset on port {PORT}")
    print(f"  Gateway: {GATEWAY_URL}")
    print(f"  Callback: {SELF_URL}/invoke\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

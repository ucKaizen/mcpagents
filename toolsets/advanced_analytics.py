"""
Toolset: Advanced Analytics

Self-registering service that provides advanced TV measurement tools:
  - get_top_programs
  - get_demographic_breakdown
  - get_cross_media_reach
  - compare_channels
  - get_genre_performance

On startup, registers with the gateway. On shutdown, deregisters.
"""

import os, sys, pathlib, asyncio

from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import uvicorn

# Add server/ to path for media_data imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "server"))

from media_data import (
    CHANNELS, PROGRAMS, GENRES, AGE_GROUPS, GENDERS,
    compute_reach, compute_share, compute_genre_performance,
    compute_top_programs, compute_demographic_breakdown, compute_cross_media,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8000")
PORT = int(os.getenv("PORT", "8003"))
SELF_URL = os.getenv("SELF_URL", f"http://127.0.0.1:{PORT}")
TOOLSET_NAME = "advanced-analytics"

# ---------------------------------------------------------------------------
# Tool definitions (schema for registration with gateway)
# ---------------------------------------------------------------------------
TOOL_DEFS = [
    {
        "name": "get_top_programs",
        "description": (
            "Get the top N programs ranked by reach or market share. "
            "Useful for questions like 'What are the most-watched programs among young women?'\n\n"
            "Args:\n"
            "  metric: Ranking metric — 'reach' (default) or 'share'\n"
            "  n: Number of top programs to return (default 10, max 25)\n"
            "  age_group: Optional. One of: '3-13', '14-29', '30-49', '50-64', '65+'\n"
            "  gender: Optional. One of: 'Male', 'Female'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "metric": {"type": "string", "description": "Ranking metric: 'reach' or 'share'"},
                "n": {"type": "integer", "description": "Number of programs to return"},
                "age_group": {"type": "string", "description": "Age group filter"},
                "gender": {"type": "string", "description": "Gender filter: Male or Female"},
            },
        },
    },
    {
        "name": "get_demographic_breakdown",
        "description": (
            "Get a full demographic breakdown (age group x gender matrix) for a program or channel. "
            "Returns reach and share for every combination of 5 age groups x 2 genders = 10 cells. "
            "Useful for understanding the audience profile.\n\n"
            "Args:\n"
            "  name: Program name (e.g. 'Tatort') or channel name (e.g. 'ZDF')\n"
            "  entity_type: Either 'program' (default) or 'channel'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Program or channel name"},
                "entity_type": {"type": "string", "description": "'program' or 'channel'"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_cross_media_reach",
        "description": (
            "Get cross-media (TV + streaming) reach for a program or channel. "
            "Returns linear TV reach, streaming/online reach, overlap, and total "
            "deduplicated reach. Streaming tends to skew younger.\n\n"
            "Args:\n"
            "  name: Program name (e.g. 'Germanys Next Topmodel') or channel name (e.g. 'RTL')\n"
            "  entity_type: Either 'program' (default) or 'channel'\n"
            "  age_group: Optional. One of: '3-13', '14-29', '30-49', '50-64', '65+'\n"
            "  gender: Optional. One of: 'Male', 'Female'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Program or channel name"},
                "entity_type": {"type": "string", "description": "'program' or 'channel'"},
                "age_group": {"type": "string", "description": "Age group filter"},
                "gender": {"type": "string", "description": "Gender filter: Male or Female"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "compare_channels",
        "description": (
            "Compare multiple TV channels side by side on a given metric. "
            "Useful for competitive analysis.\n\n"
            "Args:\n"
            "  channels: Comma-separated channel names (e.g. 'Das Erste,ZDF,RTL')\n"
            "  metric: 'share' (default) or 'reach'\n"
            "  age_group: Optional. One of: '3-13', '14-29', '30-49', '50-64', '65+'\n"
            "  gender: Optional. One of: 'Male', 'Female'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "channels": {"type": "string", "description": "Comma-separated channel names"},
                "metric": {"type": "string", "description": "'share' or 'reach'"},
                "age_group": {"type": "string", "description": "Age group filter"},
                "gender": {"type": "string", "description": "Gender filter: Male or Female"},
            },
            "required": ["channels"],
        },
    },
    {
        "name": "get_genre_performance",
        "description": (
            "Get aggregated performance metrics for all programs in a genre. "
            "Returns total reach, average share, and per-program breakdowns.\n\n"
            "Args:\n"
            "  genre: Genre name. One of: News, Crime, Entertainment, Sports, Soap, "
            "Documentary, Talk, Reality, Film\n"
            "  age_group: Optional. One of: '3-13', '14-29', '30-49', '50-64', '65+'\n"
            "  gender: Optional. One of: 'Male', 'Female'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "genre": {"type": "string", "description": "Genre name"},
                "age_group": {"type": "string", "description": "Age group filter"},
                "gender": {"type": "string", "description": "Gender filter: Male or Female"},
            },
            "required": ["genre"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def handle_get_top_programs(args: dict) -> dict:
    metric = args.get("metric", "reach")
    n = args.get("n", 10)
    age_group = args.get("age_group")
    gender = args.get("gender")
    if age_group and age_group not in AGE_GROUPS:
        return {"error": f"Invalid age_group '{age_group}'. Valid: {AGE_GROUPS}"}
    if gender and gender not in GENDERS:
        return {"error": f"Invalid gender '{gender}'. Valid: {GENDERS}"}
    if metric not in ("reach", "share"):
        return {"error": f"Invalid metric '{metric}'. Use 'reach' or 'share'."}
    n = min(max(n, 1), len(PROGRAMS))
    programs = compute_top_programs(metric, n, age_group, gender)
    return {
        "metric": metric,
        "age_group": age_group or "Total",
        "gender": gender or "Total",
        "top_programs": programs,
    }


def handle_get_demographic_breakdown(args: dict) -> dict:
    name = args.get("name", "")
    entity_type = args.get("entity_type", "program")
    if entity_type not in ("program", "channel"):
        return {"error": f"Invalid entity_type '{entity_type}'. Use 'program' or 'channel'."}
    return compute_demographic_breakdown(name, entity_type)


def handle_get_cross_media_reach(args: dict) -> dict:
    name = args.get("name", "")
    entity_type = args.get("entity_type", "program")
    age_group = args.get("age_group")
    gender = args.get("gender")
    if entity_type not in ("program", "channel"):
        return {"error": f"Invalid entity_type '{entity_type}'. Use 'program' or 'channel'."}
    if age_group and age_group not in AGE_GROUPS:
        return {"error": f"Invalid age_group '{age_group}'. Valid: {AGE_GROUPS}"}
    if gender and gender not in GENDERS:
        return {"error": f"Invalid gender '{gender}'. Valid: {GENDERS}"}
    return compute_cross_media(name, entity_type, age_group, gender)


def handle_compare_channels(args: dict) -> dict:
    channels_str = args.get("channels", "")
    metric = args.get("metric", "share")
    age_group = args.get("age_group")
    gender = args.get("gender")
    if age_group and age_group not in AGE_GROUPS:
        return {"error": f"Invalid age_group '{age_group}'. Valid: {AGE_GROUPS}"}
    if gender and gender not in GENDERS:
        return {"error": f"Invalid gender '{gender}'. Valid: {GENDERS}"}

    channel_list = [c.strip() for c in channels_str.split(",")]
    results = []
    for ch in channel_list:
        if ch not in CHANNELS:
            results.append({"channel": ch, "error": f"Channel '{ch}' not found"})
            continue
        if metric == "share":
            data = compute_share(ch, "channel", age_group, gender)
        else:
            ch_progs = [k for k, v in PROGRAMS.items() if v["channel"] == ch]
            total_reach = sum(
                compute_reach(p, age_group, gender)["reach_thousands"]
                for p in ch_progs
            )
            data = {
                "channel": ch,
                "type": CHANNELS[ch]["type"],
                "age_group": age_group or "Total",
                "gender": gender or "Total",
                "total_reach_thousands": total_reach,
                "program_count": len(ch_progs),
            }
        results.append(data)

    return {
        "metric": metric,
        "age_group": age_group or "Total",
        "gender": gender or "Total",
        "comparison": results,
    }


def handle_get_genre_performance(args: dict) -> dict:
    genre = args.get("genre", "")
    age_group = args.get("age_group")
    gender = args.get("gender")
    if age_group and age_group not in AGE_GROUPS:
        return {"error": f"Invalid age_group '{age_group}'. Valid: {AGE_GROUPS}"}
    if gender and gender not in GENDERS:
        return {"error": f"Invalid gender '{gender}'. Valid: {GENDERS}"}
    return compute_genre_performance(genre, age_group, gender)


TOOL_HANDLERS = {
    "get_top_programs": handle_get_top_programs,
    "get_demographic_breakdown": handle_get_demographic_breakdown,
    "get_cross_media_reach": handle_get_cross_media_reach,
    "compare_channels": handle_compare_channels,
    "get_genre_performance": handle_get_genre_performance,
}


# ---------------------------------------------------------------------------
# Registration with gateway
# ---------------------------------------------------------------------------
async def register_with_gateway():
    payload = {
        "toolset_name": TOOLSET_NAME,
        "callback_url": f"{SELF_URL}/invoke",
        "tools": TOOL_DEFS,
    }
    import sys
    print(f"[{TOOLSET_NAME}] CONFIG: GATEWAY_URL={GATEWAY_URL}", flush=True, file=sys.stderr)
    print(f"[{TOOLSET_NAME}] CONFIG: SELF_URL={SELF_URL}", flush=True, file=sys.stderr)
    print(f"[{TOOLSET_NAME}] CONFIG: register_url={GATEWAY_URL}/api/register", flush=True, file=sys.stderr)
    for attempt in range(10):
        try:
            print(f"[{TOOLSET_NAME}] Attempt {attempt+1}/10 ...", flush=True, file=sys.stderr)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{GATEWAY_URL}/api/register", json=payload)
                resp.raise_for_status()
                print(f"[{TOOLSET_NAME}] SUCCESS: {resp.json()}", flush=True, file=sys.stderr)
                return
        except httpx.ConnectError as e:
            print(f"[{TOOLSET_NAME}] CONNECT ERROR ({attempt+1}): {e}", flush=True, file=sys.stderr)
        except httpx.HTTPStatusError as e:
            print(f"[{TOOLSET_NAME}] HTTP ERROR ({attempt+1}): {e.response.status_code} — {e.response.text}", flush=True, file=sys.stderr)
        except Exception as e:
            print(f"[{TOOLSET_NAME}] ERROR ({attempt+1}): {type(e).__name__}: {e}", flush=True, file=sys.stderr)
        await asyncio.sleep(2)
    print(f"[{TOOLSET_NAME}] FAILED after 10 attempts", flush=True, file=sys.stderr)


async def deregister_from_gateway():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{GATEWAY_URL}/api/deregister/{TOOLSET_NAME}")
            print(f"[{TOOLSET_NAME}] Deregistered from gateway: {resp.json()}")
    except Exception as e:
        print(f"[{TOOLSET_NAME}] Deregistration failed: {e}")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title=f"Toolset: {TOOLSET_NAME}")

_registration_task = None

@app.on_event("startup")
async def on_startup():
    global _registration_task
    import sys
    print(f"[{TOOLSET_NAME}] ===== STARTUP =====", flush=True, file=sys.stderr)
    print(f"[{TOOLSET_NAME}] GATEWAY_URL={GATEWAY_URL}", flush=True, file=sys.stderr)
    print(f"[{TOOLSET_NAME}] SELF_URL={SELF_URL}", flush=True, file=sys.stderr)
    print(f"[{TOOLSET_NAME}] PORT={PORT}", flush=True, file=sys.stderr)
    _registration_task = asyncio.create_task(register_with_gateway())

@app.on_event("shutdown")
async def on_shutdown():
    await deregister_from_gateway()


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

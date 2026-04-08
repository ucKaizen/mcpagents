# server/app_mcp.py
"""
AGF Germany TV Audience Measurement — MCP Server

Exposes 9 tools for querying reach, market share, cross-media metrics,
and demographic breakdowns for German TV channels and programs.
"""

from typing import Optional
from fastmcp import FastMCP
from media_data import (
    CHANNELS, PROGRAMS, GENRES, AGE_GROUPS, GENDERS,
    compute_reach, compute_share, compute_genre_performance,
    compute_top_programs, compute_demographic_breakdown, compute_cross_media,
)

mcp = FastMCP("agf-media-measurement")


@mcp.tool
def list_channels() -> dict:
    """
    List all available German TV channels.

    Returns a list of channels with name, type (public/private), group, and description.
    Use this tool first to discover available channel names before querying metrics.
    """
    result = []
    for name, info in CHANNELS.items():
        result.append({
            "name": name,
            "type": info["type"],
            "group": info["group"],
            "description": info["description"],
        })
    return {"channels": result, "count": len(result)}


@mcp.tool
def list_programs(channel: Optional[str] = None, genre: Optional[str] = None) -> dict:
    """
    List TV programs, optionally filtered by channel and/or genre.

    Args:
        channel: Filter by channel name (e.g. "Das Erste", "RTL", "ZDF"). Optional.
        genre: Filter by genre (e.g. "News", "Crime", "Entertainment", "Sports",
               "Soap", "Documentary", "Talk", "Reality", "Film"). Optional.

    Returns a list of programs with channel, genre, timeslot, day, and duration.
    Use this to discover program names before querying detailed metrics.
    """
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
        filters = []
        if channel:
            filters.append(f"channel='{channel}'")
        if genre:
            filters.append(f"genre='{genre}'")
        return {
            "error": f"No programs found for {' and '.join(filters)}",
            "available_channels": list(CHANNELS.keys()),
            "available_genres": GENRES,
        }
    return {"programs": result, "count": len(result)}


@mcp.tool
def get_program_reach(program: str, age_group: Optional[str] = None,
                      gender: Optional[str] = None) -> dict:
    """
    Get audience reach for a specific TV program.

    Args:
        program: Exact program name (e.g. "Tatort", "Tagesschau", "GZSZ").
                 Use list_programs() to find valid names.
        age_group: Optional demographic filter. One of: "3-13", "14-29", "30-49", "50-64", "65+".
                   If omitted, returns total reach across all age groups.
        gender: Optional demographic filter. One of: "Male", "Female".
                If omitted, returns total reach across both genders.

    Returns reach in thousands, reach percentage, and average viewing minutes.
    """
    if age_group and age_group not in AGE_GROUPS:
        return {"error": f"Invalid age_group '{age_group}'. Valid: {AGE_GROUPS}"}
    if gender and gender not in GENDERS:
        return {"error": f"Invalid gender '{gender}'. Valid: {GENDERS}"}
    return compute_reach(program, age_group, gender)


@mcp.tool
def get_channel_share(channel: str, age_group: Optional[str] = None,
                      gender: Optional[str] = None) -> dict:
    """
    Get market share percentage for a TV channel.

    Market share = the percentage of all viewers watching TV at the time
    who were tuned in to this channel, averaged across the channel's programs.

    Args:
        channel: Channel name (e.g. "Das Erste", "ZDF", "RTL", "ProSieben").
                 Use list_channels() to find valid names.
        age_group: Optional demographic filter. One of: "3-13", "14-29", "30-49", "50-64", "65+".
        gender: Optional demographic filter. One of: "Male", "Female".

    Returns market share percentage for the specified demographic.
    """
    if age_group and age_group not in AGE_GROUPS:
        return {"error": f"Invalid age_group '{age_group}'. Valid: {AGE_GROUPS}"}
    if gender and gender not in GENDERS:
        return {"error": f"Invalid gender '{gender}'. Valid: {GENDERS}"}
    return compute_share(channel, "channel", age_group, gender)


@mcp.tool
def get_genre_performance(genre: str, age_group: Optional[str] = None,
                          gender: Optional[str] = None) -> dict:
    """
    Get aggregated performance metrics for all programs in a genre.

    Args:
        genre: Genre name. One of: "News", "Crime", "Entertainment", "Sports",
               "Soap", "Documentary", "Talk", "Reality", "Film".
        age_group: Optional demographic filter. One of: "3-13", "14-29", "30-49", "50-64", "65+".
        gender: Optional demographic filter. One of: "Male", "Female".

    Returns total reach, average share, and per-program breakdowns for the genre.
    """
    if age_group and age_group not in AGE_GROUPS:
        return {"error": f"Invalid age_group '{age_group}'. Valid: {AGE_GROUPS}"}
    if gender and gender not in GENDERS:
        return {"error": f"Invalid gender '{gender}'. Valid: {GENDERS}"}
    return compute_genre_performance(genre, age_group, gender)


@mcp.tool
def get_top_programs(metric: str = "reach", n: int = 10,
                     age_group: Optional[str] = None,
                     gender: Optional[str] = None) -> dict:
    """
    Get the top N programs ranked by reach or market share.

    Args:
        metric: Ranking metric — "reach" (default) or "share".
        n: Number of top programs to return (default 10, max 25).
        age_group: Optional demographic filter. One of: "3-13", "14-29", "30-49", "50-64", "65+".
        gender: Optional demographic filter. One of: "Male", "Female".

    Returns a ranked list of programs with reach and share metrics.
    Useful for questions like "What are the most-watched programs among young women?"
    """
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


@mcp.tool
def get_demographic_breakdown(name: str, entity_type: str = "program") -> dict:
    """
    Get a full demographic breakdown (age group x gender matrix) for a program or channel.

    Args:
        name: Program name (e.g. "Tatort") or channel name (e.g. "ZDF").
        entity_type: Either "program" (default) or "channel".

    Returns a matrix with reach and/or share for every combination of
    5 age groups x 2 genders = 10 demographic cells.
    Useful for understanding the audience profile of a program or channel.
    """
    if entity_type not in ("program", "channel"):
        return {"error": f"Invalid entity_type '{entity_type}'. Use 'program' or 'channel'."}
    return compute_demographic_breakdown(name, entity_type)


@mcp.tool
def get_cross_media_reach(name: str, entity_type: str = "program",
                          age_group: Optional[str] = None,
                          gender: Optional[str] = None) -> dict:
    """
    Get cross-media (TV + streaming) reach for a program or channel.

    Returns linear TV reach, streaming/online reach, overlap, and total
    deduplicated reach. Streaming tends to skew younger.

    Args:
        name: Program name (e.g. "Germanys Next Topmodel") or channel name (e.g. "RTL").
        entity_type: Either "program" (default) or "channel".
        age_group: Optional demographic filter. One of: "3-13", "14-29", "30-49", "50-64", "65+".
        gender: Optional demographic filter. One of: "Male", "Female".

    Returns TV reach, streaming reach, overlap, and total deduplicated reach
    in thousands and as a percentage.
    """
    if entity_type not in ("program", "channel"):
        return {"error": f"Invalid entity_type '{entity_type}'. Use 'program' or 'channel'."}
    if age_group and age_group not in AGE_GROUPS:
        return {"error": f"Invalid age_group '{age_group}'. Valid: {AGE_GROUPS}"}
    if gender and gender not in GENDERS:
        return {"error": f"Invalid gender '{gender}'. Valid: {GENDERS}"}
    return compute_cross_media(name, entity_type, age_group, gender)


@mcp.tool
def compare_channels(channels: str, metric: str = "share",
                     age_group: Optional[str] = None,
                     gender: Optional[str] = None) -> dict:
    """
    Compare multiple TV channels side by side on a given metric.

    Args:
        channels: Comma-separated channel names (e.g. "Das Erste,ZDF,RTL").
                  Use list_channels() to find valid names.
        metric: Comparison metric — "share" (default) or "reach".
        age_group: Optional demographic filter. One of: "3-13", "14-29", "30-49", "50-64", "65+".
        gender: Optional demographic filter. One of: "Male", "Female".

    Returns side-by-side comparison of the specified channels.
    """
    if age_group and age_group not in AGE_GROUPS:
        return {"error": f"Invalid age_group '{age_group}'. Valid: {AGE_GROUPS}"}
    if gender and gender not in GENDERS:
        return {"error": f"Invalid gender '{gender}'. Valid: {GENDERS}"}

    channel_list = [c.strip() for c in channels.split(",")]
    results = []
    for ch in channel_list:
        if ch not in CHANNELS:
            results.append({"channel": ch, "error": f"Channel '{ch}' not found"})
            continue
        if metric == "share":
            data = compute_share(ch, "channel", age_group, gender)
        else:
            # Sum reach across all programs on the channel
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


@mcp.resource("res://health")
def health() -> dict:
    return {"ok": True, "server": "agf-media-measurement"}


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000, path="/mcp")

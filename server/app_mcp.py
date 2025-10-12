# server/app_mcp.py
from typing import Optional
from fastmcp import FastMCP

mcp = FastMCP("hello-mcp")

# NOTE: Depending on your fastmcp version, you may need @mcp.tool() instead of @mcp.tool
@mcp.tool
def calculate_reach(campaign_id: str) -> dict:
    """
    Calculate estimated reach for a given campaign.

    Args:
        campaign_id: Unique identifier of the campaign.

    Returns:
        A dictionary with:
            - campaign_id: The provided campaign ID.
            - estimated_reach: A deterministic numeric metric derived from the ID.
            - message: A summary string.
    """
    # Simple deterministic logic — always produces same result for same ID
    estimated_reach = (sum(ord(c) for c in campaign_id) * 1000) % 1_000_000

    return {
        "message": f"Estimated reach calculated for campaign {campaign_id}.",
        "campaign_id": campaign_id,
        "estimated_reach": estimated_reach,
    }


@mcp.tool
def calculate_brand_lift(campaign_id: str) -> dict:
    """
    Calculate brand lift for a given campaign.

    Args:
        campaign_id: Unique identifier of the campaign.

    Returns:
        A dictionary with:
            - campaign_id: The provided campaign ID.
            - brand_lift_percentage: A deterministic percentage value derived from the ID.
            - message: A summary string.
    """
    # Deterministic brand lift based on campaign ID
    brand_lift_percentage = (sum(ord(c) for c in campaign_id) % 20) + 1  # 1–20%

    return {
        "message": f"Brand lift calculated for campaign {campaign_id}.",
        "campaign_id": campaign_id,
        "brand_lift_percentage": brand_lift_percentage,
    }



#  Use a valid URI for resources (must include a scheme)
@mcp.resource("res://health")
def health() -> dict:
    return {"ok": True, "server": "hello-mcp"}

if __name__ == "__main__":
    # HTTP transport with explicit MCP path
    mcp.run(transport="http", host="0.0.0.0", port=8000, path="/mcp")

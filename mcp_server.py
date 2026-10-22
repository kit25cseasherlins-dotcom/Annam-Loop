"""
MCP Server for Annam Loop - Food Rescue and Redistribution.
Runs over Streamable HTTP on port 8000 at path /mcp.
Implements the Model Context Protocol (spec 2025-11-25+).
"""

import os
import json
from typing import List, Dict, Any, Optional

try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.mcpserver import MCPServer as FastMCP

import services

# Initialize database schema if not present
services.init_db()

# Create FastMCP server instance
mcp = FastMCP(
    name=" ReFeed Food Rescue",
    instructions="MCP tools to list surplus food, find available food nearby, reserve food portions, and manage food waste redistribution for canteens and messes."
)

# Configure host and port for streamable-http transport
mcp.settings.host = os.environ.get("MCP_HOST", "127.0.0.1")
mcp.settings.port = int(os.environ.get("MCP_PORT", "8000"))
mcp.settings.streamable_http_path = "/mcp"


@mcp.tool()
def list_surplus_food(
    name: str,
    quantity: int,
    unit: str = "parcel",
    price_per_unit: float = 0.0,
    canteen: str = "My Canteen"
) -> Dict[str, Any]:
    """
    List surplus food available from a canteen for rescue and redistribution.

    Args:
        name: Name of the food item (e.g., 'Mutton biryani', 'Chapati & Kurma', 'Idli')
        quantity: Number of portions/units available (must be >= 1)
        unit: Unit of measurement (e.g., 'parcel', 'plate', 'kg', 'box')
        price_per_unit: Price in rupees per unit (0 for free surplus food)
        canteen: Name of the canteen or mess (default: 'My Canteen')

    Returns:
        The created listing with id, name, quantity, unit, price, posted_at, safe_until, and distance_km.
    """
    return services.list_food(
        name=name,
        quantity=quantity,
        unit=unit,
        price_per_unit=price_per_unit,
        canteen=canteen
    )


@mcp.tool()
def find_food(
    sort: str = "distance",
    max_results: int = 10
) -> List[Dict[str, Any]]:
    """
    Find live listings of surplus food, nearest first, excluding expired, removed, or sold out items.

    Args:
        sort: Sorting order: 'distance' (nearest first, default), 'price' (cheapest first), or 'newest'
        max_results: Maximum number of listings to return (default: 10)

    Returns:
        List of available food listings with canteen details, distance in km, safe until window, and prices.
    """
    return services.find_food(sort=sort, max_results=max_results)


@mcp.tool()
def reserve_food(
    listing_id: int,
    customer_name: str = "Guest"
) -> Dict[str, Any]:
    """
    Reserve one portion of surplus food from a listing.
    Decrements quantity by one, records the reservation, and returns the unique pickup code and updated quantity.
    Returns a clear error if the item is sold out, expired, or removed.

    Args:
        listing_id: The ID of the food listing to reserve
        customer_name: Name of the customer placing the reservation (default: 'Guest')

    Returns:
        Reservation confirmation containing pickup_code, updated_quantity, and listing details, or an error.
    """
    return services.reserve_food(listing_id=listing_id, customer_name=customer_name)


@mcp.tool()
def remove_food(
    listing_id: int
) -> Dict[str, Any]:
    """
    Remove a food listing so it immediately disappears from Find food.
    Used by canteens/donors to cancel or remove an active surplus listing.

    Args:
        listing_id: The ID of the listing to remove

    Returns:
        Confirmation indicating whether the listing was removed.
    """
    return services.remove_food(listing_id=listing_id)


@mcp.tool()
def get_stats() -> Dict[str, int]:
    """
    Get live system statistics: total live listings, total portions available, and total portions reserved.

    Returns:
        Dictionary with 'live_listings', 'portions_available', and 'portions_reserved'.
    """
    return services.get_stats()


@mcp.resource("stats://live")
def live_stats_resource() -> str:
    """Live statistics resource returning JSON of live listings, portions available, and portions reserved."""
    return json.dumps(services.get_stats())


if __name__ == "__main__":
    print(f"Starting Annam Loop MCP Server on http://{mcp.settings.host}:{mcp.settings.port}/mcp ...")
    mcp.run(transport="streamable-http")

"""ReFeed MCP server (Streamable HTTP). Run: python server.py  ->  http://localhost:8000/mcp"""
import threading, time
from mcp.server.fastmcp import FastMCP
import core

mcp = FastMCP("ReFeed", host="0.0.0.0", port=8000, stateless_http=True, json_response=True)

@mcp.tool()
def log_surplus(provider_name: str, area: str, food_item: str, quantity: float, unit: str = "plates") -> dict:
    """A food provider reports leftover food (e.g. 20 plates of biryani). Rejects unknown food types for safety."""
    return core.log_surplus(provider_name, area, food_item, quantity, unit)

@mcp.tool()
def get_safe_window(food_item: str) -> dict:
    """How many hours this food stays safe, from a fixed food-safety rulebook."""
    return core.get_safe_window(food_item)

@mcp.tool()
def find_nearby_surplus(area: str) -> dict:
    """List safe, unexpired surplus food available in an area."""
    return core.find_nearby_surplus(area)

@mcp.tool()
def claim_food(listing_id: str, claimer_name: str) -> dict:
    """Reserve a listing for a student, canteen, NGO or other person."""
    return core.claim_food(listing_id, claimer_name)

@mcp.tool()
def expire_listings() -> dict:
    """Remove food whose safe time is over and mark it as waste."""
    return core.expire_listings()

@mcp.tool()
def get_waste_by_region(area: str) -> dict:
    """For biogas partners: what food waste is available in a region. Returns a spoken_message to read aloud."""
    return core.get_waste_by_region(area)

@mcp.tool()
def accept_waste_pickup(area: str, partner_name: str) -> dict:
    """A biogas partner confirms pickup of all waste in a region."""
    return core.accept_waste_pickup(area, partner_name)

@mcp.tool()
def get_impact_stats() -> dict:
    """Totals for the dashboard: meals rescued, kg sent to biogas, estimated methane avoided."""
    return core.get_impact_stats()

def _expiry_loop():
    while True:
        core.expire_listings()
        time.sleep(10)

if __name__ == "__main__":
    threading.Thread(target=_expiry_loop, daemon=True).start()
    mcp.run(transport="streamable-http")

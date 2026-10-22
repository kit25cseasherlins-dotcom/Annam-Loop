"""
Complete Verification Script for Annam Loop.
Tests all requirements specified in the prompt:
1. MCP Server running over Streamable HTTP on port 8000 (MCP spec 2025-11-25+), testing all tools.
2. Voice Assistant as Donor: "mutton biryani, three parcels, 20 rupees each" -> confirmed on Find food page.
3. Voice Assistant as Customer: "what food is near me" and "reserve the first one" -> confirms portion decrease & stats update.
4. Voice Assistant as Donor: "remove mutton biryani" -> confirms removal from Find food page.
"""

import os
import sys
import time
import subprocess
import asyncio
import json

from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

import seed

# Seed initial database
seed.seed_database()

# Start MCP Server in background
print("\n" + "=" * 60)
print("TEST 1: Starting MCP Server on http://127.0.0.1:8000/mcp ...")
print("=" * 60)

mcp_proc = subprocess.Popen(
    [sys.executable, "mcp_server.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

time.sleep(2.5)

async def test_mcp_server():
    async with streamable_http_client("http://127.0.0.1:8000/mcp") as (read, write, *_):
        async with ClientSession(read, write) as session:
            init_res = await session.initialize()
            print(f"[OK] Negotiated Protocol Version: {init_res.protocolVersion}")
            assert init_res.protocolVersion >= "2025-11-25", "Protocol version should be 2025-11-25 or later"

            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"[OK] Tools available on MCP Server: {tool_names}")
            assert "list_surplus_food" in tool_names
            assert "find_food" in tool_names
            assert "reserve_food" in tool_names
            assert "remove_food" in tool_names
            assert "get_stats" in tool_names

            # 1. Test get_stats
            res_stats = await session.call_tool("get_stats", {})
            stats_data = json.loads(res_stats.content[0].text)
            print(f"[OK] Tool 'get_stats' output: {stats_data}")

            # 2. Test find_food
            res_find = await session.call_tool("find_food", {"sort": "distance", "max_results": 3})
            find_data = [json.loads(c.text) for c in res_find.content]
            print(f"[OK] Tool 'find_food' returned {len(find_data)} items. Nearest: {find_data[0]['name']} ({find_data[0]['distance_km']} km)")

            # 3. Test list_surplus_food
            res_list = await session.call_tool("list_surplus_food", {
                "name": "Test Pongal",
                "quantity": 5,
                "unit": "parcel",
                "price_per_unit": 10.0,
                "canteen": "Annapoorna Mess"
            })
            list_data = json.loads(res_list.content[0].text)
            print(f"[OK] Tool 'list_surplus_food' created listing #{list_data['id']}: {list_data['name']} (Safe until: {list_data['safe_until']})")

            # 4. Test reserve_food
            res_reserve = await session.call_tool("reserve_food", {
                "listing_id": list_data["id"],
                "customer_name": "Test Customer"
            })
            reserve_data = json.loads(res_reserve.content[0].text)
            print(f"[OK] Tool 'reserve_food' pickup code: {reserve_data['pickup_code']}, updated quantity: {reserve_data['updated_quantity']}")
            assert reserve_data["updated_quantity"] == 4

            # 5. Test remove_food
            res_remove = await session.call_tool("remove_food", {"listing_id": list_data["id"]})
            remove_data = json.loads(res_remove.content[0].text)
            print(f"[OK] Tool 'remove_food' result: {remove_data['message']}")

try:
    asyncio.run(test_mcp_server())
except Exception as e:
    mcp_proc.terminate()
    raise e

# Now test Flask App Endpoints
print("\n" + "=" * 60)
print("TEST 2: Testing Voice Assistant & Flask Web App Workflow ...")
print("=" * 60)

from app import app
client = app.test_client()

# Re-seed database
seed.seed_database()

# Step 2: In the app, as Donor: say "mutton biryani, three parcels, 20 rupees each"
print("\n--- Step 2: Donor voice listing ---")
resp2 = client.post("/api/assistant", json={
    "transcript": "mutton biryani, three parcels, 20 rupees each",
    "role": "donor"
})
assert resp2.status_code == 200
data2 = resp2.get_json()
print("Spoken reply:", data2["reply_text"])
print("Tool called:", data2["tool_name"], "with args:", data2["tool_args"])
assert data2["tool_name"] == "list_surplus_food"
assert data2["tool_args"]["quantity"] == 3
assert data2["tool_args"]["price_per_unit"] == 20.0
created_listing_id = data2["tool_result"]["id"]
print(f"Created listing ID: #{created_listing_id}")

# Confirm the listing appears on the Find food page
resp_find = client.get("/find")
assert b"Mutton Biryani" in resp_find.data
print("[CONFIRMED] 'Mutton Biryani' listing is visible on /find HTML page!")

# Step 3: As Customer: say "what food is near me", then reserve one item
print("\n--- Step 3: Customer search and reservation ---")
stats_before = client.get("/api/stats").get_json()
print("Stats before reservation:", stats_before)

resp3_find = client.post("/api/assistant", json={
    "transcript": "what food is near me",
    "role": "customer"
})
assert resp3_find.status_code == 200
data3_find = resp3_find.get_json()
print("Spoken reply for search:", data3_find["reply_text"])
assert data3_find["tool_name"] == "find_food"

# Reserve one item
resp3_reserve = client.post("/api/assistant", json={
    "transcript": "reserve the first one",
    "role": "customer"
})
assert resp3_reserve.status_code == 200
data3_res = resp3_reserve.get_json()
print("Spoken reply for reservation:", data3_res["reply_text"])
print("Pickup Code:", data3_res["tool_result"]["pickup_code"])
assert data3_res["tool_name"] == "reserve_food"

stats_after = client.get("/api/stats").get_json()
print("Stats after reservation:", stats_after)
assert stats_after["portions_available"] == stats_before["portions_available"] - 1
assert stats_after["portions_reserved"] == stats_before["portions_reserved"] + 1
print("[CONFIRMED] Portions available dropped by 1 and portions reserved increased by 1!")

# Step 4: As Donor: remove a listing by voice and confirm it disappears from Find food
print("\n--- Step 4: Donor remove listing by voice ---")
resp4 = client.post("/api/assistant", json={
    "transcript": "remove mutton biryani",
    "role": "donor"
})
assert resp4.status_code == 200
data4 = resp4.get_json()
print("Spoken reply for removal:", data4["reply_text"])
assert data4["tool_name"] == "remove_food"
assert data4["tool_result"]["listing_id"] == created_listing_id

import services
active_ids = [i["id"] for i in services.find_food()]
assert created_listing_id not in active_ids
print(f"[CONFIRMED] Listing #{created_listing_id} (Mutton Biryani) removed and no longer in active listings!")

# Clean up MCP server
mcp_proc.terminate()
mcp_proc.wait()

print("\n" + "=" * 60)
print("ALL VERIFICATION CHECKS PASSED SUCCESSFULLY! (100% OK)")
print("=" * 60)

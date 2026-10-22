"""
Assistant engine for Annam Loop.
Connects to the MCP server at http://127.0.0.1:8000/mcp via streamable HTTP.
Supports optional LLM-based tool calling or robust rule-based parsing fallback.
"""

import os
import re
import json
import asyncio
import httpx
from typing import Dict, Any, Tuple, Optional, List

from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

import services

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")

# Word to number mapping
WORD_TO_NUM = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100
}


def words_to_int(text: str) -> Optional[int]:
    """Convert string number or number words (e.g. 'three', '25', 'twenty five') to integer."""
    text = text.strip().lower()
    if text.isdigit():
        return int(text)

    tokens = text.split()
    total = 0
    current = 0
    found = False
    for t in tokens:
        if t in WORD_TO_NUM:
            found = True
            val = WORD_TO_NUM[t]
            if val == 100:
                current = (current or 1) * 100
            else:
                current += val
        elif t.isdigit():
            found = True
            current += int(t)
    total += current
    return total if found else None


def parse_tool_result_content(tool_result: Any) -> Any:
    """Extract structured data or JSON from MCP CallToolResult."""
    data = None
    if hasattr(tool_result, "structuredContent") and tool_result.structuredContent is not None:
        sc = tool_result.structuredContent
        if isinstance(sc, dict) and "result" in sc:
            data = sc["result"]
        else:
            data = sc
    elif hasattr(tool_result, "content") and tool_result.content:
        parsed_items = []
        for c in tool_result.content:
            text = getattr(c, "text", None) or (c.get("text") if isinstance(c, dict) else str(c))
            try:
                parsed_items.append(json.loads(text))
            except Exception:
                parsed_items.append(text)
        if len(parsed_items) == 1:
            data = parsed_items[0]
        else:
            data = parsed_items

    if isinstance(data, dict) and "result" in data and len(data) == 1:
        data = data["result"]

    return data if data is not None else str(tool_result)


def rule_based_parser(transcript: str, role: str) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
    """
    Fallback parser for natural voice commands.
    Returns (tool_name, tool_args, polite_error_message).
    """
    raw = transcript.strip()
    text = raw.lower()

    # Normalize punctuation
    cleaned = re.sub(r"[,;!?]", " ", text)

    # 1. Stats command
    if any(k in cleaned for k in ["stats", "statistics", "how many portions", "how many listings", "summary", "dashboard stats"]):
        return "get_stats", {}, None

    # 2. Find food commands (Customer)
    if any(k in cleaned for k in [
        "what food is near me", "what food near me", "food near me",
        "find food", "show food", "available food", "what is available",
        "nearest food", "hungry", "any food", "search food", "browse food",
        "உணவு", "கிடைக்கும் உணவு"
    ]):
        if role == "donor":
            return None, {}, "As a Donor, you can list surplus food or remove your listings. Switch to Customer to find and reserve food."
        return "find_food", {"sort": "distance", "max_results": 10}, None

    # 3. Reserve food commands (Customer)
    if any(cleaned.startswith(k) or f" {k} " in f" {cleaned} " for k in ["reserve", "book", "order", "get", "claim", "take", "முன்பதிவு"]):
        if role == "donor":
            return None, {}, "As a Donor, you cannot reserve food. Please switch your role to Customer to reserve meals."

        live = services.find_food(sort="distance", max_results=10)
        if not live:
            return None, {}, "Sorry, there are currently no active food listings available to reserve."

        # Case A: "reserve the first one", "book the nearest one", "reserve 1st", "order the first"
        if any(w in cleaned for w in ["first", "nearest", "1st", "first one", "closest"]):
            target_id = live[0]["id"]
            return "reserve_food", {"listing_id": target_id, "customer_name": "Guest Customer"}, None

        # Case B: "reserve second", "2nd"
        if any(w in cleaned for w in ["second", "2nd"]):
            if len(live) >= 2:
                return "reserve_food", {"listing_id": live[1]["id"], "customer_name": "Guest Customer"}, None
            return None, {}, "There is only one listing available."

        # Case C: By ID directly: "reserve listing 3", "reserve id 2", "reserve 2"
        id_match = re.search(r"\b(?:listing|item|id)?\s*#?(\d+)\b", cleaned)
        if id_match:
            try:
                lid = int(id_match.group(1))
                return "reserve_food", {"listing_id": lid, "customer_name": "Guest Customer"}, None
            except ValueError:
                pass

        # Case D: By item name: "book chapati", "reserve mutton biryani", "reserve idli"
        for item in live:
            dish_name = item["name"].lower()
            dish_words = [w for w in dish_name.split() if len(w) > 2]
            if any(w in cleaned for w in dish_words) or dish_name in cleaned:
                return "reserve_food", {"listing_id": item["id"], "customer_name": "Guest Customer"}, None

        # Fallback to first if general reserve
        return "reserve_food", {"listing_id": live[0]["id"], "customer_name": "Guest Customer"}, None

    # 4. Remove food commands (Donor)
    if any(cleaned.startswith(k) or f" {k} " in f" {cleaned} " for k in ["remove", "delete", "cancel", "take down", "நீக்கு"]):
        if role == "customer":
            return None, {}, "As a Customer, you can reserve food. To remove a surplus food listing, please switch to the Donor role."

        # Check by ID
        id_match = re.search(r"\b(?:listing|item|id)?\s*#?(\d+)\b", cleaned)
        if id_match:
            lid = int(id_match.group(1))
            return "remove_food", {"listing_id": lid}, None

        # Check by name matching active listings (prefer newest)
        live = services.find_food(sort="newest", max_results=20)
        for item in live:
            dish_name = item["name"].lower()
            dish_words = [w for w in dish_name.split() if len(w) > 2]
            if any(w in cleaned for w in dish_words) or dish_name in cleaned:
                return "remove_food", {"listing_id": item["id"]}, None

        return None, {}, "Could not determine which listing to remove. Please specify the food name or listing ID."
    # Broad find-food intent for customers
    if role == "customer" and any(w in cleaned.split() for w in [
        "near", "nearby", "find", "show", "available", "search",
        "browse", "hungry", "food", "any", "what"
    ]):
        return "find_food", {"sort": "distance", "max_results": 10}, None
    
    # 5. List surplus food commands (Donor)
    has_list_intent = any(k in cleaned for k in ["list", "donate", "add", "have", "surplus", "parcel", "plate", "rupee", "rs", "பட்டியலிடு"]) or (role == "donor")

    if has_list_intent:
        if role == "customer":
            return None, {}, "As a Customer, you cannot list food. Switch to the Donor role to donate surplus food."

        price = 0.0
        if "free" in cleaned:
            price = 0.0
        else:
            price_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:rupees|rupee|rs|inr|₹)", cleaned)
            if not price_match:
                word_price_match = re.search(r"([a-z]+)\s*(?:rupees|rupee|rs|inr|₹)", cleaned)
                if word_price_match:
                    num_val = words_to_int(word_price_match.group(1))
                    if num_val is not None:
                        price = float(num_val)
            else:
                price = float(price_match.group(1))

        unit = "parcel"
        unit_match = re.search(r"\b(parcel|parcels|plate|plates|kg|kgs|kilo|kilos|cup|cups|box|boxes|portion|portions)\b", cleaned)
        if unit_match:
            raw_u = unit_match.group(1).rstrip("s")
            if raw_u in ["kilo"]:
                unit = "kg"
            else:
                unit = raw_u

        quantity = 1
        qty_pattern = rf"(\d+|{'|'.join(WORD_TO_NUM.keys())})\s*(?:{unit}|{unit}s|parcels?|plates?|portions?|boxes?|cups?|kgs?)"
        qty_match = re.search(qty_pattern, cleaned)
        if qty_match:
            q_val = words_to_int(qty_match.group(1))
            if q_val and q_val > 0:
                quantity = q_val
        else:
            for w in cleaned.split():
                val = words_to_int(w)
                if val and val > 0 and val < 500 and val != int(price):
                    quantity = val
                    break

        tokens_to_remove = [
            r"\b(list|donate|add|surplus|food|portions?|please|here|canteen|my canteen|mess)\b",
            r"\b\d+\s*(?:rupees|rupee|rs|inr|₹)\s*(?:each|per parcel|per plate)?\b",
            r"\b[a-z]+\s*(?:rupees|rupee|rs|inr|₹)\s*(?:each|per parcel|per plate)?\b",
            r"\b(?:rupees|rupee|rs|inr|₹)\s*\d+\b",
            r"\b(?:each|per parcel|per plate|for free|free)\b",
            rf"\b(?:\d+|{'|'.join(WORD_TO_NUM.keys())})\s*(?:{unit}|{unit}s)\b",
            rf"\b(?:{unit}|{unit}s)\b",
            r"\b(?:\d+)\b"
        ]
        name_candidate = cleaned
        for pat in tokens_to_remove:
            name_candidate = re.sub(pat, " ", name_candidate, flags=re.IGNORECASE)

        name_candidate = re.sub(r"\s+", " ", name_candidate).strip()
        if not name_candidate:
            name_candidate = "Surplus Meals"
        else:
            name_candidate = name_candidate.title()

        return "list_surplus_food", {
            "name": name_candidate,
            "quantity": quantity,
            "unit": unit,
            "price_per_unit": price,
            "canteen": "My Canteen"
        }, None
    if role == "donor":
        return None, {}, f"I heard: '{raw}'. I didn't quite catch that. As a Donor, you can say 'List 5 parcels of Biryani for 30 rupees' or 'Remove listing 1'."
    else:
        return None, {}, f"I heard: '{raw}'. I didn't quite catch that. As a Customer, you can say 'What food is near me' or 'Reserve the first one'."

async def parse_with_llm(transcript: str, role: str, available_tools: List[Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Attempt to use an LLM provider if configured to choose tool and arguments.
    Falls back gracefully if anything fails or no API key is provided.
    """
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return None

    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    formatted_tools = []
    for t in available_tools:
        formatted_tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema if hasattr(t, "inputSchema") else {"type": "object", "properties": {}}
            }
        })

    system_prompt = f"""You are the voice assistant for Annam Loop (food rescue app).
The current user role is: '{role}'.
Allowed tools for '{role}':
- If role is 'donor': list_surplus_food, remove_food, get_stats.
- If role is 'customer': find_food, reserve_food, get_stats.
Select the appropriate tool and arguments based strictly on the user transcript. If role is not allowed, do not call forbidden tools.
"""

    try:
        base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcript}
            ],
            "tools": formatted_tools,
            "tool_choice": "auto"
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                msg = data["choices"][0]["message"]
                if "tool_calls" in msg and msg["tool_calls"]:
                    call = msg["tool_calls"][0]
                    t_name = call["function"]["name"]
                    t_args = json.loads(call["function"]["arguments"] or "{}")
                    return t_name, t_args
    except Exception:
        pass

    return None


async def call_mcp_client(tool_name: str, tool_args: Dict[str, Any]) -> Any:
    """Connect to MCP server via Streamable HTTP and call specified tool."""
    async with streamable_http_client(MCP_SERVER_URL) as (read, write, *_):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, tool_args)
            return parse_tool_result_content(result)


async def execute_assistant_request(transcript: str, role: str) -> Dict[str, Any]:
    """
    Main entry point for assistant requests.
    Validates role, chooses tool (via LLM or rule-based parser), calls MCP tool,
    and returns formatted chat reply.
    """
    role = (role or "customer").lower()

    tool_name = None
    tool_args = {}
    error_msg = None

    # Check available tools from MCP server
    mcp_tools = []
    try:
        async with streamable_http_client(MCP_SERVER_URL) as (read, write, *_):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tool_list_resp = await session.list_tools()
                mcp_tools = tool_list_resp.tools
    except Exception:
        pass

    # Try LLM if configured
    if mcp_tools:
        llm_choice = await parse_with_llm(transcript, role, mcp_tools)
        if llm_choice:
            tool_name, tool_args = llm_choice

    # Fallback to rule-based parser if LLM didn't return a call
    if not tool_name:
        tool_name, tool_args, error_msg = rule_based_parser(transcript, role)

    if error_msg:
        return {
            "reply_text": error_msg,
            "tool_name": None,
            "tool_args": {},
            "tool_result": None
        }

    # Role permission check
    allowed_tools = {
        "donor": ["list_surplus_food", "remove_food", "get_stats"],
        "customer": ["find_food", "reserve_food", "get_stats"]
    }

    if tool_name not in allowed_tools.get(role, []):
        if role == "customer":
            polite = "As a Customer, you can discover and reserve surplus meals. To list or remove food, please switch to the Donor role."
        else:
            polite = "As a Donor, you can list and manage surplus food. Switch to the Customer role to search and reserve meals."
        return {
            "reply_text": polite,
            "tool_name": None,
            "tool_args": {},
            "tool_result": None
        }

    # Call MCP tool
    try:
        tool_result = await call_mcp_client(tool_name, tool_args)
    except Exception as e:
        return {
            "reply_text": f"Error communicating with MCP server: {str(e)}",
            "tool_name": tool_name,
            "tool_args": tool_args,
            "tool_result": {"error": str(e)}
        }

    # Formulate natural spoken reply
    spoken_reply = format_spoken_reply(tool_name, tool_args, tool_result)

    return {
        "reply_text": spoken_reply,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "tool_result": tool_result
    }


def format_spoken_reply(tool_name: str, tool_args: Dict[str, Any], result: Any) -> str:
    """Generate friendly, spoken-style responses."""
    if tool_name == "list_surplus_food":
        name = result.get("name", tool_args.get("name", "food"))
        qty = result.get("quantity", tool_args.get("quantity", 1))
        unit = result.get("unit", "parcel")
        price = result.get("price", 0)
        canteen = result.get("canteen", "My Canteen")
        price_str = f"₹{price:.0f}" if price > 0 else "free of charge"
        return f"Great news! I have listed {qty} {unit} of {name} from {canteen} at {price_str}. It is now available for nearby customers to rescue."

    elif tool_name == "find_food":
        items = result if isinstance(result, list) else result.get("result", [])
        if not items:
            return "I couldn't find any surplus food available nearby right now. Please check back shortly!"
        nearest = items[0]
        count = len(items)
        return f"I found {count} surplus food listing{'s' if count > 1 else ''} near you. The nearest is {nearest['name']} at {nearest['canteen']}, just {nearest['distance_km']} kilometers away for ₹{nearest['price']:.0f}."

    elif tool_name == "reserve_food":
        if isinstance(result, dict) and not result.get("success", True):
            return f"I'm sorry, I could not complete that reservation: {result.get('error', 'Item unavailable')}."
        name = result.get("name", "your meal")
        canteen = result.get("canteen", "the mess")
        code = result.get("pickup_code", "AL-0000")
        qty_left = result.get("updated_quantity", 0)
        return f"Your reservation for {name} at {canteen} is confirmed! Your pickup code is {code}. Show this at the counter to collect your food. {qty_left} portions remaining."

    elif tool_name == "remove_food":
        if isinstance(result, dict) and not result.get("success", True):
            return f"Could not remove listing: {result.get('error', 'Listing not found')}."
        name = result.get("name", "")
        lid = result.get("listing_id", tool_args.get("listing_id"))
        return f"Listing #{lid}{f' ({name})' if name else ''} has been successfully removed and is no longer visible to customers."

    elif tool_name == "get_stats":
        live = result.get("live_listings", 0)
        portions = result.get("portions_available", 0)
        reserved = result.get("portions_reserved", 0)
        return f"Current Annam Loop stats: {live} active listings with {portions} portions available for rescue, and {reserved} portions already reserved."

    return "Done! The operation completed successfully."

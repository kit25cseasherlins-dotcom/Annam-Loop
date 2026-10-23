# 🌿 ReFeed

ReFeed is a localized surplus food rescue and redistribution web platform designed for small canteens, messes, and local eateries. It connects surplus food providers (Donors) with local community members and students (Customers) to reduce cooked food waste, promote meal redistribution, and ensure meals are consumed within defined freshness windows.

The application incorporates a simulated Alexa+ Voice Assistant Experience in a modern web interface, allowing hands-free voice operations to list food, discover nearby surplus dishes, and reserve meal portions powered by the Model Context Protocol (MCP) over Streamable HTTP.

---
## 📺 Demo Video

[![Watch the ReFeed Vedio]](https://youtu.be/SEKOkt4w2Hs?si=6FJwhVJ3bxX9juK0)

## 🏛️ Architecture Overview

The system operates around a single source of truth:

```
┌────────────────────────────────────────────────────────┐
│                   Shared Database                      │
│                 SQLite (Refeed.db)                      │
└───────────────────────────┬────────────────────────────┘
                            │
               ┌────────────┴────────────┐
               │  Shared services.py     │
               │  - list_food            │
               │  - find_food            │
               │  - reserve_food         │
               │  - remove_food          │
               │  - get_stats            │
               └──────┬────────────┬─────┘
                      │            │
         ┌────────────┘            └────────────┐
         ▼                                      ▼
┌─────────────────────────┐           ┌─────────────────────────┐
│   Flask Web App         │           │   FastMCP Server        │
│   (Port 5000)           │           │   (Port 8000)           │
│   - Home (/): Stats     │           │   - Streamable HTTP     │
│   - Find Food (/find)   │           │   - Path: /mcp          │
│   - Donate (/donate)    │           │   - Spec: 2025-11-25+   │
│   - Assistant (/assistant)          └────────────▲────────────┘
└───────────┬─────────────┘                        │
            │                                      │
            └────────── MCP Python Client ─────────┘
                   (POST /api/assistant)
```

1. **Shared SQLite Layer (`Refeed.db` & `services.py`)**:
   - Both the web application and the MCP server share identical business logic and database state.
   - Any food listed, reserved, or removed via voice or web reflects immediately on both the Find Food page and the Home page live statistics.
   - Enforces food safety consumption windows (e.g., Rice/Gravy 4h, Snacks 6h, Sweets 8h). Expired items are strictly excluded from search.
   - Maintains mock canteen distances (e.g., Annapoorna Mess: 0.4 km, Murugan Mess: 1.2 km, Aavin Cafeteria: 2.5 km, Buhari Express: 3.8 km) ensuring visible nearest-first ordering.

2. **Official FastMCP Server (`mcp_server.py`)**:
   - Built with the official Python MCP SDK (`mcp[cli]`).
   - Serves over **Streamable HTTP** on port `8000` at path `/mcp` (`http://127.0.0.1:8000/mcp`).
   - Implements MCP specification `2025-11-25` or later.
   - Exposes typed tools with detailed docstrings for LLM reasoning and execution.

3. **Voice Assistant Screen (`/assistant`)**:
   - Simulates the hands-free **Alexa+ conversational experience** in a web browser.
   - Big centered mic with pulsing animation powered by the browser Web Speech API (`SpeechRecognition`).
   - Supports bilingual speech recognition: **English (`en-IN`)** and **Tamil (`ta-IN`)**.
   - Accessible fallback: live editable transcript text box with manual Send button.
   - Full Text-to-Speech playback (`window.speechSynthesis`) with a dedicated mute toggle button.
   - Transparent MCP Inspector panels: displays executed MCP tool name, arguments, and return payload alongside interactive visual food cards.

---

## 🛠️ MCP Tools Reference

The MCP Server exposes the following tools over Streamable HTTP:

1. **`list_surplus_food(name: str, quantity: int, unit: str = "parcel", price_per_unit: float = 0, canteen: str = "My Canteen") -> dict`**
   - Creates a surplus food listing with safe window calculation and mock distance.
   - Returns: `{ id, name, quantity, unit, price, posted_at, safe_until, distance_km }`.

2. **`find_food(sort: str = "distance", max_results: int = 10) -> list[dict]`**
   - Returns live listings nearest first, excluding items that are expired, removed, or sold out.

3. **`reserve_food(listing_id: int, customer_name: str = "Guest") -> dict`**
   - Decrements portion quantity by one, records the reservation, and returns a unique pickup code (e.g., `AL-1-7492`).
   - Returns clear error feedback if the item is sold out or expired.

4. **`remove_food(listing_id: int) -> dict`**
   - Removes an active listing so it immediately disappears from customer search.

5. **`get_stats() -> dict`**
   - Returns real-time platform statistics: `live_listings`, `portions_available`, and `portions_reserved`.
   - Also accessible as MCP resource `stats://live`.

---

## 🗣️ Sample Voice Commands

The assistant provides role-based permission enforcement:
- **Donor**: Can list surplus food, remove listings, and check stats.
- **Customer**: Can find nearby food, reserve meals, and check stats.

### For Donors:
- `"Mutton biryani, three parcels, 20 rupees each"`
- `"List 5 plates of Idli for 15 rupees"`
- `"Donate 4 parcels of Sambar rice"`
- `"Remove mutton biryani"`
- `"Remove listing 1"`

### For Customers:
- `"What food is near me"`
- `"Find food"`
- `"Reserve the first one"`
- `"Book chapati"`
- `"Reserve mutton biryani"`
- `"How many portions available"`

> **Automatic Fallback:** The backend connects to an optional LLM provider (OpenAI, Gemini, Groq, Ollama) if `LLM_API_KEY` is provided. If no key is set or the network fails, a deterministic natural-language parser ensures the demo never breaks.

---

## 🚀 Installation & Setup

### Prerequisites
- Python 3.10+
- Node.js & npm (for MCP Inspector testing)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
*(No API key is needed to run; the built-in rule-based fallback works out of the box!)*

### 3. Seed Realistic Sample Data
```bash
python seed.py
```
This loads sample items (*Chapati & Kurma, Sambar rice, Idli, Mutton biryani*) at varying distances (0.4 km – 3.8 km).

---

## 🏃 Running the Application

### Option A: Run Both Services Concurrently (Recommended)
Use the included runner script to launch both the Flask Web App and the MCP Server together:
```bash
python run.py
```
- **Flask App:** [http://127.0.0.1:5000](http://127.0.0.1:5000)
- **MCP Server:** [http://127.0.0.1:8000/mcp](http://127.0.0.1:8000/mcp)

Press `Ctrl+C` to terminate both cleanly.

### Option B: Run Services Separately in Two Terminals

**Terminal 1 — MCP Server:**
```bash
python mcp_server.py
```

**Terminal 2 — Flask Web App:**
```bash
python app.py
```

---

## 🧪 Testing with MCP Inspector

You can inspect and execute all 4 MCP tools using the official MCP Inspector:
```bash
npx @modelcontextprotocol/inspector
```
1. In the Inspector UI, select transport: **Streamable HTTP**.
2. Connect to URL: `http://127.0.0.1:8000/mcp`.
3. Test calling `get_stats`, `find_food`, `list_surplus_food`, `reserve_food`, and `remove_food`.

---

## 🎨 Visual Identity

- **Navbar**: Dark Forest Green (`#143829`)
- **Primary Buttons & Highlights**: Vibrant Indian Saffron (`#e67e22`)
- **Background**: Soft Off-White (`#fcfbf7`)
- **Layout**: Rounded cards (`border-radius: 14px`) with subtle elevation shadows

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).

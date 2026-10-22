"""
Shared data access layer and business logic for Annam Loop.
Used by both the Flask web application and the MCP server.
Stores listings and reservations in SQLite (annam.db).
"""

import os
import sqlite3
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "annam.db")

# Default safe windows in hours based on food category
SAFE_WINDOWS = {
    "rice/gravy": 4,
    "meals": 4,
    "biryani": 4,
    "curry": 4,
    "tiffin": 4,
    "snacks": 6,
    "sweets": 8,
    "bakery": 8,
    "default": 4
}

# Known mock canteen distances in kilometers
CANTEEN_DISTANCES = {
    "Annapoorna Mess": 0.4,
    "Murugan Mess": 1.2,
    "Aavin Cafeteria": 2.5,
    "Buhari Express": 3.8,
    "Saravana Mess": 1.5,
    "Sangeetha Canteen": 0.9,
    "My Canteen": 0.5
}


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database tables if they do not already exist."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit TEXT NOT NULL DEFAULT 'parcel',
        price_per_unit REAL NOT NULL DEFAULT 0.0,
        canteen TEXT NOT NULL DEFAULT 'My Canteen',
        food_type TEXT NOT NULL DEFAULT 'rice/gravy',
        distance_km REAL NOT NULL DEFAULT 1.0,
        posted_at TEXT NOT NULL,
        safe_until TEXT NOT NULL,
        is_removed INTEGER NOT NULL DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        listing_id INTEGER NOT NULL,
        customer_name TEXT NOT NULL DEFAULT 'Guest',
        pickup_code TEXT NOT NULL,
        reserved_at TEXT NOT NULL,
        FOREIGN KEY (listing_id) REFERENCES listings (id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS canteens (
        name TEXT PRIMARY KEY,
        distance_km REAL NOT NULL
    )
    """)

    # Populate default canteen distances if table empty
    cur.execute("SELECT COUNT(*) FROM canteens")
    if cur.fetchone()[0] == 0:
        for name, dist in CANTEEN_DISTANCES.items():
            cur.execute("INSERT INTO canteens (name, distance_km) VALUES (?, ?)", (name, dist))

    conn.commit()
    conn.close()


def get_canteen_distance(canteen: str, db_path: Optional[str] = None) -> float:
    """Look up mock distance for a canteen, or assign and store a consistent distance."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT distance_km FROM canteens WHERE name = ?", (canteen,))
    row = cur.fetchone()
    if row:
        dist = row["distance_km"]
        conn.close()
        return float(dist)

    # Check hardcoded fallback or assign deterministic distance
    if canteen in CANTEEN_DISTANCES:
        dist = CANTEEN_DISTANCES[canteen]
    else:
        # Mock distance between 0.3 and 4.5 km based on canteen name hash
        dist = round(0.3 + (abs(hash(canteen)) % 40) / 10.0, 1)

    cur.execute("INSERT OR REPLACE INTO canteens (name, distance_km) VALUES (?, ?)", (canteen, dist))
    conn.commit()
    conn.close()
    return dist


def determine_food_type(name: str) -> str:
    """Infer food type from dish name for safe window calculation."""
    try:
        import safety
        cat = safety.classify_food(name)
        if cat in ("cooked_rice", "curry"):
            return "rice/gravy"
        elif cat == "dry_dish":
            return "tiffin"
        elif cat == "snack":
            return "snacks"
        elif cat in ("dairy", "fruit_veg"):
            return "sweets"
    except Exception:
        pass

    name_lower = name.lower()
    if any(k in name_lower for k in ["snack", "samosa", "pakoda", "bajji", "vada", "roll", "puff"]):
        return "snacks"
    if any(k in name_lower for k in ["sweet", "halwa", "laddu", "payasam", "kesari", "cake", "bun", "bread"]):
        return "sweets"
    if any(k in name_lower for k in ["idli", "dosa", "poori", "pongal", "upma"]):
        return "tiffin"
    if any(k in name_lower for k in ["biryani", "briyani", "pulao", "rice", "curry", "kurma", "gravy", "sambar", "dal", "chapati"]):
        return "rice/gravy"
    return "default"


def list_food(
    name: str,
    quantity: int,
    unit: str = "parcel",
    price_per_unit: float = 0.0,
    canteen: str = "My Canteen",
    food_type: Optional[str] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    List surplus food available from a canteen.
    Returns the created listing record.
    """
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    now = datetime.now()
    if not food_type:
        food_type = determine_food_type(name)

    hours = SAFE_WINDOWS.get(food_type.lower(), SAFE_WINDOWS["default"])
    safe_until_dt = now + timedelta(hours=hours)

    posted_at_str = now.strftime("%Y-%m-%d %H:%M:%S")
    safe_until_str = safe_until_dt.strftime("%Y-%m-%d %H:%M:%S")

    distance_km = get_canteen_distance(canteen, db_path)

    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO listings (name, quantity, unit, price_per_unit, canteen, food_type, distance_km, posted_at, safe_until, is_removed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
    """, (name.strip(), int(quantity), unit.strip(), float(price_per_unit), canteen.strip(), food_type, distance_km, posted_at_str, safe_until_str))
    listing_id = cur.lastrowid
    conn.commit()
    conn.close()

    return {
        "id": listing_id,
        "name": name.strip(),
        "quantity": int(quantity),
        "unit": unit.strip(),
        "price": float(price_per_unit),
        "canteen": canteen.strip(),
        "food_type": food_type,
        "distance_km": distance_km,
        "posted_at": posted_at_str,
        "safe_until": safe_until_str
    }


def find_food(
    sort: str = "distance",
    max_results: int = 10,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Find live listings of surplus food, excluding expired, removed, or sold-out items.
    Default sort is nearest first (distance).
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    order_clause = "distance_km ASC"
    if sort == "price":
        order_clause = "price_per_unit ASC, distance_km ASC"
    elif sort == "newest":
        order_clause = "id DESC"

    query = f"""
        SELECT id, name, quantity, unit, price_per_unit, canteen, food_type, distance_km, posted_at, safe_until
        FROM listings
        WHERE is_removed = 0
          AND quantity > 0
          AND safe_until > ?
        ORDER BY {order_clause}
        LIMIT ?
    """
    cur.execute(query, (now_str, int(max_results)))
    rows = cur.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "id": r["id"],
            "name": r["name"],
            "quantity": r["quantity"],
            "unit": r["unit"],
            "price": float(r["price_per_unit"]),
            "canteen": r["canteen"],
            "food_type": r["food_type"],
            "distance_km": float(r["distance_km"]),
            "posted_at": r["posted_at"],
            "safe_until": r["safe_until"]
        })
    return results


def reserve_food(
    listing_id: int,
    customer_name: str = "Guest",
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Reserve one portion from a listing.
    Decrements quantity by one, records the reservation, and returns pickup code and updated quantity.
    Returns clear error if sold out, expired, or not found.
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id, name, quantity, unit, price_per_unit, canteen, safe_until, is_removed FROM listings WHERE id = ?", (listing_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return {"success": False, "error": f"Listing #{listing_id} not found."}

    if row["is_removed"] == 1:
        conn.close()
        return {"success": False, "error": f"Item '{row['name']}' has been removed by the donor."}

    if row["quantity"] <= 0:
        conn.close()
        return {"success": False, "error": f"Item '{row['name']}' is sold out."}

    if row["safe_until"] <= now_str:
        conn.close()
        return {"success": False, "error": f"Item '{row['name']}' has passed its safe consumption window."}

    # Decrement quantity
    new_quantity = row["quantity"] - 1
    cur.execute("UPDATE listings SET quantity = ? WHERE id = ?", (new_quantity, listing_id))

    # Generate unique pickup code (e.g., AL-7492)
    rand_code = random.randint(1000, 9999)
    pickup_code = f"AL-{listing_id}-{rand_code}"

    cur.execute("""
        INSERT INTO reservations (listing_id, customer_name, pickup_code, reserved_at)
        VALUES (?, ?, ?, ?)
    """, (listing_id, customer_name.strip() or "Guest", pickup_code, now_str))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "listing_id": listing_id,
        "name": row["name"],
        "canteen": row["canteen"],
        "unit": row["unit"],
        "price": float(row["price_per_unit"]),
        "pickup_code": pickup_code,
        "updated_quantity": new_quantity,
        "message": f"Successfully reserved 1 {row['unit']} of {row['name']} at {row['canteen']}. Pickup code: {pickup_code}"
    }


def remove_food(
    listing_id: int,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Remove a listing so it disappears from Find food.
    """
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, name, canteen, is_removed FROM listings WHERE id = ?", (listing_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return {"success": False, "error": f"Listing #{listing_id} not found."}

    if row["is_removed"] == 1:
        conn.close()
        return {"success": True, "listing_id": listing_id, "message": f"Listing #{listing_id} was already removed."}

    cur.execute("UPDATE listings SET is_removed = 1 WHERE id = ?", (listing_id,))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "listing_id": listing_id,
        "name": row["name"],
        "canteen": row["canteen"],
        "message": f"Listing #{listing_id} ('{row['name']}') removed successfully."
    }


def get_stats(db_path: Optional[str] = None) -> Dict[str, int]:
    """
    Returns live listings, portions available, and portions reserved.
    Excludes removed or expired items from live listings & portions available.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(quantity), 0)
        FROM listings
        WHERE is_removed = 0
          AND quantity > 0
          AND safe_until > ?
    """, (now_str,))
    live_row = cur.fetchone()
    live_listings = live_row[0] if live_row else 0
    portions_available = live_row[1] if live_row else 0

    cur.execute("SELECT COUNT(*) FROM reservations")
    res_row = cur.fetchone()
    portions_reserved = res_row[0] if res_row else 0

    conn.close()
    return {
        "live_listings": int(live_listings),
        "portions_available": int(portions_available),
        "portions_reserved": int(portions_reserved)
    }


def seed_initial_data(db_path: Optional[str] = None, force: bool = False) -> None:
    """Seed sample data if database is empty or force=True."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM listings")
    count = cur.fetchone()[0]
    conn.close()

    if count > 0 and not force:
        return

    sample_items = [
        {
            "name": "Chapati & Kurma",
            "quantity": 12,
            "unit": "parcel",
            "price_per_unit": 25.0,
            "canteen": "Annapoorna Mess",
            "food_type": "rice/gravy"
        },
        {
            "name": "Sambar rice",
            "quantity": 8,
            "unit": "parcel",
            "price_per_unit": 20.0,
            "canteen": "Murugan Mess",
            "food_type": "rice/gravy"
        },
        {
            "name": "Idli",
            "quantity": 15,
            "unit": "plate",
            "price_per_unit": 15.0,
            "canteen": "Aavin Cafeteria",
            "food_type": "tiffin"
        },
        {
            "name": "Mutton biryani",
            "quantity": 6,
            "unit": "parcel",
            "price_per_unit": 60.0,
            "canteen": "Buhari Express",
            "food_type": "biryani"
        }
    ]

    for item in sample_items:
        list_food(
            name=item["name"],
            quantity=item["quantity"],
            unit=item["unit"],
            price_per_unit=item["price_per_unit"],
            canteen=item["canteen"],
            food_type=item["food_type"],
            db_path=db_path
        )


if __name__ == "__main__":
    init_db()
    seed_initial_data()
    print("Database initialized and seeded.")
    print("Live stats:", get_stats())
    print("Sample food nearby:", find_food(max_results=3))

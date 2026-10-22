"""ReFeed business logic. In-memory store (swap for DynamoDB later - see README)."""
import time, uuid, threading
from safety import classify_food, safe_window_seconds, SAFE_HOURS

_lock = threading.Lock()
LISTINGS: dict[str, dict] = {}
KG_PER_UNIT = {"plates": 0.4, "plate": 0.4, "portions": 0.3, "kg": 1.0, "liters": 1.0, "litres": 1.0}
METHANE_KG_PER_KG_FOOD = 0.5   # rough placeholder estimate for dashboard; state it as an estimate

def _now(): return time.time()
def _norm(s): return s.strip().lower()

def get_safe_window(food_item: str) -> dict:
    cat = classify_food(food_item)
    if cat is None:
        return {"ok": False, "reason": "Unknown food type. For safety it cannot be listed."}
    return {"ok": True, "category": cat, "safe_hours": SAFE_HOURS[cat],
            "safe_seconds": safe_window_seconds(cat)}

def log_surplus(provider_name: str, area: str, food_item: str, quantity: float, unit: str = "plates") -> dict:
    w = get_safe_window(food_item)
    if not w["ok"]:
        return w
    if quantity <= 0:
        return {"ok": False, "reason": "Quantity must be more than zero."}
    lid = uuid.uuid4().hex[:8]
    now = _now()
    rec = {"id": lid, "provider": provider_name, "area": area, "food": food_item,
           "category": w["category"], "quantity": quantity, "unit": unit,
           "kg": round(quantity * KG_PER_UNIT.get(unit.lower(), 0.4), 2),
           "created_at": now, "expires_at": now + w["safe_seconds"],
           "status": "available", "claimed_by": None, "collected_by": None}
    with _lock:
        LISTINGS[lid] = rec
    return {"ok": True, "listing": rec}

def expire_listings() -> dict:
    """Move unclaimed, out-of-time food to 'waste'. Food never goes back to consumers."""
    now, moved = _now(), []
    with _lock:
        for r in LISTINGS.values():
            if r["status"] == "available" and r["expires_at"] <= now:
                r["status"] = "waste"
                moved.append(r["id"])
    return {"ok": True, "expired_to_waste": moved}

def find_nearby_surplus(area: str) -> dict:
    expire_listings()
    now = _now()
    with _lock:
        items = [dict(r, minutes_left=max(0, int((r["expires_at"] - now) / 60)))
                 for r in LISTINGS.values()
                 if r["status"] == "available" and _norm(r["area"]) == _norm(area)]
    return {"ok": True, "count": len(items), "listings": items}

def claim_food(listing_id: str, claimer_name: str) -> dict:
    expire_listings()
    with _lock:
        r = LISTINGS.get(listing_id)
        if not r:
            return {"ok": False, "reason": "Listing not found."}
        if r["status"] != "available":
            return {"ok": False, "reason": f"Not available (status: {r['status']})."}
        r["status"], r["claimed_by"] = "claimed", claimer_name
        return {"ok": True, "listing": dict(r)}

def get_waste_by_region(area: str) -> dict:
    expire_listings()
    with _lock:
        items = [dict(r) for r in LISTINGS.values() if r["status"] == "waste" and _norm(r["area"]) == _norm(area)]
    total = round(sum(r["kg"] for r in items), 1)
    msg = (f"There are {total} kg of cooked food waste in {area}. Do you want to collect it?"
           if items else f"There is no food waste in {area} right now.")
    return {"ok": True, "area": area, "total_kg": total, "count": len(items), "listings": items, "spoken_message": msg}

def accept_waste_pickup(area: str, partner_name: str) -> dict:
    expire_listings()
    taken = []
    with _lock:
        for r in LISTINGS.values():
            if r["status"] == "waste" and _norm(r["area"]) == _norm(area):
                r["status"], r["collected_by"] = "collected_biogas", partner_name
                taken.append(r["id"])
    kg = round(sum(LISTINGS[i]["kg"] for i in taken), 1)
    return {"ok": True, "partner": partner_name, "collected_ids": taken, "total_kg": kg}

def get_impact_stats() -> dict:
    expire_listings()
    with _lock:
        rows = list(LISTINGS.values())
    rescued = sum(r["kg"] for r in rows if r["status"] == "claimed")
    biogas = sum(r["kg"] for r in rows if r["status"] in ("waste", "collected_biogas"))
    return {"ok": True, "rescued_kg": round(rescued, 1), "meals_rescued": int(rescued / 0.4),
            "sent_to_biogas_kg": round(biogas, 1),
            "est_methane_avoided_kg": round(biogas * METHANE_KG_PER_KG_FOOD, 1),
            "note": "Methane figure is a rough estimate."}

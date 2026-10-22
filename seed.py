"""
Database seed script for Annam Loop.
Populates SQLite (annam.db) with realistic sample surplus food items at various distances:
  - Chapati & Kurma (Annapoorna Mess, 0.4 km)
  - Sambar rice (Murugan Mess, 1.2 km)
  - Idli (Aavin Cafeteria, 2.5 km)
  - Mutton biryani (Buhari Express, 3.8 km)
"""

import os
import sys

# Ensure UTF-8 output if supported
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import services

def seed_database():
    print("[*] Seeding Annam Loop database...")
    # Initialize DB schema
    services.init_db()

    # Clear existing listings and reservations to ensure a clean slate
    conn = services.get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM reservations")
    cur.execute("DELETE FROM listings")
    conn.commit()
    conn.close()

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
        created = services.list_food(
            name=item["name"],
            quantity=item["quantity"],
            unit=item["unit"],
            price_per_unit=item["price_per_unit"],
            canteen=item["canteen"],
            food_type=item["food_type"]
        )
        print(f"  + Listed: {created['name']} ({created['quantity']} {created['unit']}s) from {created['canteen']} - {created['distance_km']} km away")

    stats = services.get_stats()
    print("\n[OK] Seeding complete!")
    print(f"  - Live Listings:      {stats['live_listings']}")
    print(f"  - Portions Available: {stats['portions_available']}")
    print(f"  - Portions Reserved:  {stats['portions_reserved']}")

if __name__ == "__main__":
    seed_database()

"""
Annam Loop - Flask Web Application
Food rescue and redistribution for small canteens and messes.
Runs locally at http://127.0.0.1:5000.
"""

import os
import asyncio
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

import services
import assistant_engine

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "annamloop-secret-key-2026")

# Initialize database schema and initial realistic sample data
services.init_db()
services.seed_initial_data()


@app.context_processor
def inject_role():
    """Make current active role available to all Jinja templates."""
    role = session.get("role", "customer")
    return {"current_role": role}


@app.route("/set-role", methods=["POST"])
def set_role():
    """Update viewing role (Donor / Customer)."""
    new_role = request.form.get("role", "customer").lower()
    if new_role in ["donor", "customer"]:
        session["role"] = new_role
    return redirect(request.referrer or url_for("index"))


@app.route("/")
def index():
    """Home page with hero, available now card, and live stats."""
    stats = services.get_stats()
    nearest_items = services.find_food(sort="distance", max_results=1)
    featured_item = nearest_items[0] if nearest_items else None

    return render_template(
        "index.html",
        stats=stats,
        featured_item=featured_item
    )


@app.route("/donate", methods=["GET", "POST"])
def donate():
    """Donate food page: donor lists surplus food and manages active listings."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        quantity_str = request.form.get("quantity", "1").strip()
        unit = request.form.get("unit", "parcel").strip()
        price_str = request.form.get("price_per_unit", "0").strip()
        canteen = request.form.get("canteen", "My Canteen").strip() or "My Canteen"
        food_type = request.form.get("food_type", "rice/gravy").strip()

        try:
            quantity = int(quantity_str)
            price = float(price_str)
            if not name:
                flash("Food name is required.", "danger")
            elif quantity <= 0:
                flash("Quantity must be at least 1.", "danger")
            else:
                new_item = services.list_food(
                    name=name,
                    quantity=quantity,
                    unit=unit,
                    price_per_unit=price,
                    canteen=canteen,
                    food_type=food_type
                )
                flash(f"Successfully listed {quantity} {unit} of '{name}' for redistribution!", "success")
                return redirect(url_for("donate"))
        except ValueError as e:
            flash(f"Invalid input: {str(e)}", "danger")

    # Fetch active listings to display to donor
    active_listings = services.find_food(sort="newest", max_results=50)
    return render_template("donate.html", listings=active_listings)


@app.route("/find")
def find():
    """Find food page: customer discovers and reserves food, nearest first."""
    sort = request.args.get("sort", "distance").lower()
    if sort not in ["distance", "price", "newest"]:
        sort = "distance"

    items = services.find_food(sort=sort, max_results=50)
    return render_template("find.html", items=items, current_sort=sort)


@app.route("/reserve/<int:listing_id>", methods=["POST"])
def reserve_route(listing_id: int):
    """Reserve a portion from a listing."""
    res = services.reserve_food(listing_id=listing_id, customer_name="Customer")
    if res.get("success"):
        flash(f"Reserved! Your Pickup Code: {res['pickup_code']}. Show this at {res['canteen']} to collect your {res['name']}.", "success")
    else:
        flash(res.get("error", "Unable to reserve portion."), "danger")
    return redirect(request.referrer or url_for("find"))


@app.route("/remove/<int:listing_id>", methods=["POST"])
def remove_route(listing_id: int):
    """Remove a listing from active surplus pool."""
    res = services.remove_food(listing_id=listing_id)
    if res.get("success"):
        flash(res.get("message", "Listing removed."), "success")
    else:
        flash(res.get("error", "Unable to remove listing."), "danger")
    return redirect(request.referrer or url_for("donate"))


@app.route("/assistant")
def assistant_page():
    """Voice Assistant page (simulated Alexa+ experience)."""
    return render_template("assistant.html")


@app.route("/api/assistant", methods=["POST"])
def api_assistant():
    """
    Assistant endpoint:
    Receives { transcript, role }.
    Calls MCP server over streamable HTTP client and returns reply, tool details, and results.
    """
    data = request.get_json(force=True, silent=True) or {}
    transcript = data.get("transcript", "").strip()
    role = data.get("role") or session.get("role", "customer")
    print("HEARD:", repr(transcript), "ROLE:", role)

    if not transcript:
        return jsonify({
            "reply_text": "I didn't hear anything. Please try speaking again or type your command.",
            "tool_name": None,
            "tool_args": {},
            "tool_result": None
        })

    # Run async MCP assistant engine
    try:
        response = asyncio.run(assistant_engine.execute_assistant_request(transcript, role))
    except Exception as e:
        response = {
            "reply_text": f"Error communicating with assistant: {str(e)}",
            "tool_name": None,
            "tool_args": {},
            "tool_result": {"error": str(e)}
        }

    return jsonify(response)


@app.route("/api/stats")
def api_stats():
    """Live stats endpoint for dynamic UI updates."""
    return jsonify(services.get_stats())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Annam Loop Flask App on http://127.0.0.1:{port} ...")
    app.run(host="127.0.0.1", port=port, debug=True)

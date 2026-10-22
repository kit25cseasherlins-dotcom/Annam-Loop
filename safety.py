"""Rule-based food safety. The AI never decides safe hours - it only helps identify the food type."""
import os, json

# category -> safe hours after cooking (conservative; edit with a food-safety source before real use)
SAFE_HOURS = {
    "cooked_rice": 3,     # rice, biryani, pulao, sadam
    "curry": 4,           # sambar, kuzhambu, gravy, dal
    "dry_dish": 5,        # poriyal, fry, chapati, parotta, dosa, idli
    "snack": 8,           # biscuits, bread, packed items
    "fruit_veg": 6,       # cut fruit, salad
    "dairy": 2,           # curd, milk sweets, payasam
}

KEYWORDS = {
    "cooked_rice": ["rice", "biryani", "biriyani", "pulao", "sadam", "sambar rice", "curd rice", "lemon rice", "fried rice"],
    "curry": ["sambar", "kuzhambu", "kulambu", "curry", "gravy", "dal", "rasam", "kurma", "kootu"],
    "dry_dish": ["poriyal", "fry", "chapati", "chapathi", "parotta", "dosa", "idli", "upma", "pongal", "vada", "noodles"],
    "snack": ["biscuit", "bread", "bun", "packed", "chips"],
    "fruit_veg": ["fruit", "salad", "banana", "vegetable"],
    "dairy": ["curd", "thayir", "milk", "payasam", "paal", "sweet", "halwa"],
}

def classify_food(food_text: str):
    """Return a category or None. Keywords first, then Bedrock (optional). Unknown -> None -> rejected."""
    t = food_text.lower()
    # check rice first so "curd rice" is rice, not dairy
    for cat in ["cooked_rice", "curry", "dry_dish", "snack", "fruit_veg", "dairy"]:
        if any(k in t for k in KEYWORDS[cat]):
            return cat
    return _bedrock_classify(food_text)

def _bedrock_classify(food_text: str):
    model = os.getenv("BEDROCK_MODEL_ID")
    if not model:
        return None
    try:
        import boto3
        client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "ap-south-1"))
        prompt = (
            "Classify this food (may be Tamil/Tanglish) into exactly one of: "
            + ", ".join(SAFE_HOURS) + ", unknown. Reply with the single word only.\nFood: " + food_text
        )
        r = client.converse(modelId=model, messages=[{"role": "user", "content": [{"text": prompt}]}],
                            inferenceConfig={"maxTokens": 10, "temperature": 0})
        out = r["output"]["message"]["content"][0]["text"].strip().lower()
        return out if out in SAFE_HOURS else None   # anything uncertain is rejected
    except Exception:
        return None

def safe_window_seconds(category: str) -> int:
    demo = os.getenv("DEMO_SECONDS")          # e.g. DEMO_SECONDS=60 so judges see expiry live
    if demo:
        return int(demo)
    return int(SAFE_HOURS[category] * 3600)

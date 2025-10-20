# pip install flask transformers torch --upgrade
# Optional (for better aliasing): pip install rapidfuzz

from flask import Flask, request, jsonify
from transformers import pipeline
import re

app = Flask(__name__)

# 1) Small NER model (fast, ~110M params)
# Alternatives: "Davlan/bert-base-multilingual-cased-ner-hrl" (multilingual, slightly larger)
ner = pipeline("token-classification",
               model="dslim/bert-base-NER",
               aggregation_strategy="simple")  # returns merged entity spans

# 2) Minimal alias/normalization map (extend this for your domain)
# Lowercase keys; values are canonical brand names.
BRAND_ALIASES = {
    # Samsung
    "samsung": "Samsung",
    "galaxy": "Samsung",
    "z fold": "Samsung",
    "fold": "Samsung",
    # Apple
    "apple": "Apple",
    "iphone": "Apple",
    "ipad": "Apple",
    # Google
    "google": "Google",
    "pixel": "Google",
    # OnePlus
    "oneplus": "OnePlus",
    # Xiaomi
    "xiaomi": "Xiaomi",
    "mi": "Xiaomi",
    "redmi": "Xiaomi",
    # Huawei
    "huawei": "Huawei",
    # LG
    "lg": "LG",
    # Sony
    "sony": "Sony",
    # Dell
    "dell": "Dell",
}

def normalize_brand(surface: str) -> str | None:
    s = surface.lower().strip()
    s = re.sub(r"\s+", " ", s)
    # exact / prefix matches over 1–2 word keys
    candidates = []
    for alias, canon in BRAND_ALIASES.items():
        if s == alias or s.startswith(alias) or alias in s.split():
            candidates.append(canon)
    if candidates:
        # pick the most frequent canonical (ties: first)
        return max(set(candidates), key=candidates.count)
    return None

def extract_brand(text: str):
    """
    Returns a concise JSON-able dict with brand, surface span, confidence, method.
    """
    if not text or not text.strip():
        return {"brand": None, "surface": None, "confidence": 0.0, "method": "none"}

    ents = ner(text)
    # Look for PRODUCT or ORG first
    ents_sorted = sorted(ents, key=lambda e: e.get("score", 0), reverse=True)

    # Pass 1: prefer PRODUCT spans (often model lines)
    for e in ents_sorted:
        if e["entity_group"] in {"PRODUCT"}:
            surface = e["word"]
            brand = normalize_brand(surface) or normalize_brand(text)
            if brand:
                return {"brand": brand, "surface": surface, "confidence": round(float(e["score"]), 3), "method": "ner+alias"}
    # Pass 2: accept ORG spans as brand directly
    for e in ents_sorted:
        if e["entity_group"] in {"ORG"}:
            surface = e["word"]
            brand = normalize_brand(surface) or surface.title()
            return {"brand": brand, "surface": surface, "confidence": round(float(e["score"]), 3), "method": "ner"}

    # Fallback: try alias lookup on the whole text (handles “galaxy fold 5”, etc.)
    brand = normalize_brand(text)
    if brand:
        return {"brand": brand, "surface": None, "confidence": 0.6, "method": "alias-only"}

    return {"brand": None, "surface": None, "confidence": 0.0, "method": "none"}

@app.route("/extract_brand", methods=["POST"])
def extract_brand_route():
    text = request.json.get("text", "")
    result = extract_brand(text)
    return jsonify(result)

if __name__ == "__main__":
    # e.g. curl -X POST localhost:8000/extract_brand -H "Content-Type: application/json" \
    #      -d '{"text":"battery life of galaxy fold 5"}'
    app.run(host="0.0.0.0", port=8000)

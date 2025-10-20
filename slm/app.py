# app.py
# pip install flask transformers torch pyyaml rapidfuzz --upgrade

from __future__ import annotations
from flask import Flask, request, jsonify
from transformers import pipeline
from rapidfuzz import process, fuzz
import yaml, re, os, time
from typing import Dict, List, Any, Optional, Tuple

CONFIG_PATH = os.environ.get("BRAND_CONFIG", "brands.yml")
MODEL_NAME = os.environ.get("NER_MODEL", "dslim/bert-base-NER")

app = Flask(__name__)

# -----------------------------
# Model (small, fast NER)
# -----------------------------
ner = pipeline(
    "token-classification",
    model=MODEL_NAME,
    aggregation_strategy="simple"
)

# -----------------------------
# Config + helpers
# -----------------------------
class BrandConfig:
    def __init__(self, data: Dict[str, Any]) -> None:
        # canonical brand names
        self.brands: List[str] = data.get("brands", [])
        # alias -> canonical map (lowercase keys)
        self.aliases: Dict[str, str] = {
            k.lower(): v for k, v in data.get("aliases", {}).items()
        }
        # regex hints (compiled), each maps to a canonical brand
        self.regex_hints: List[Tuple[re.Pattern, str]] = []
        for hint in data.get("regex_hints", []):
            pat = re.compile(hint["pattern"], flags=re.I)
            self.regex_hints.append((pat, hint["brand"]))
        # thresholds
        thr = data.get("thresholds", {})
        self.ner_min_conf: float = float(thr.get("ner_min_conf", 0.70))
        self.fuzzy_min_score: float = float(thr.get("fuzzy_min_score", 86))

        # fuzzy candidate list for RapidFuzz
        self._fuzzy_keys = list(self.aliases.keys())

    def alias_lookup(self, text: str) -> Optional[str]:
        s = " ".join(text.lower().split())
        # 1) exact / contains (split) check
        if s in self.aliases:
            return self.aliases[s]
        for token in s.split():
            if token in self.aliases:
                return self.aliases[token]
        # 2) fuzzy (helps with typos)
        if self._fuzzy_keys:
            match = process.extractOne(
                s, self._fuzzy_keys, scorer=fuzz.WRatio
            )
            if match and match[1] >= self.fuzzy_min_score:
                return self.aliases.get(match[0])
        return None

    def regex_hint_lookup(self, text: str) -> Optional[str]:
        for pat, brand in self.regex_hints:
            if pat.search(text):
                return brand
        return None


_config_mtime = 0.0
CONFIG: BrandConfig

def _load_config() -> BrandConfig:
    global _config_mtime
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _config_mtime = os.path.getmtime(CONFIG_PATH)
    return BrandConfig(data)

def _maybe_reload_config() -> None:
    global _config_mtime, CONFIG
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
        if mtime > _config_mtime:
            CONFIG = _load_config()
    except FileNotFoundError:
        pass

# initial load
CONFIG = _load_config()

# -----------------------------
# Core extraction
# -----------------------------
def _pick_best_entity(ents: List[Dict[str, Any]], preferred: set[str]) -> Optional[Dict[str, Any]]:
    # pick highest-score entity among preferred groups
    candidates = [e for e in ents if e.get("entity_group") in preferred]
    if not candidates:
        return None
    return max(candidates, key=lambda e: e.get("score", 0.0))

def extract_brand(text: str) -> Dict[str, Any]:
    if not text or not text.strip():
        return {"brand": None, "surface": None, "confidence": 0.0, "method": "none"}

    # First, regex hints (cheap + explicit)
    hint_brand = CONFIG.regex_hint_lookup(text)
    if hint_brand:
        return {"brand": hint_brand, "surface": None, "confidence": 0.95, "method": "regex-hint"}

    ents = ner(text)
    ents = sorted(ents, key=lambda e: e.get("score", 0.0), reverse=True)

    # Prefer PRODUCT span (often model names), else ORG
    e_prod = _pick_best_entity(ents, {"PRODUCT"})
    e_org  = _pick_best_entity(ents, {"ORG"})

    # Pass 1: PRODUCT span -> alias/brand resolution
    if e_prod and e_prod["score"] >= CONFIG.ner_min_conf:
        surface = e_prod["word"]
        brand = CONFIG.alias_lookup(surface) or CONFIG.alias_lookup(text)
        if brand:
            return {
                "brand": brand, "surface": surface,
                "confidence": round(float(e_prod["score"]), 3),
                "method": "ner(product)+alias"
            }

    # Pass 2: ORG span -> direct brand or alias normalization
    if e_org and e_org["score"] >= CONFIG.ner_min_conf:
        surface = e_org["word"]
        brand = CONFIG.alias_lookup(surface) or surface.title()
        return {
            "brand": brand, "surface": surface,
            "confidence": round(float(e_org["score"]), 3),
            "method": "ner(org)"
        }

    # Fallbacks: alias over full text (handles “galaxy fold 5”)
    brand = CONFIG.alias_lookup(text)
    if brand:
        return {"brand": brand, "surface": None, "confidence": 0.70, "method": "alias-only"}

    return {"brand": None, "surface": None, "confidence": 0.0, "method": "none"}

# -----------------------------
# Routes
# -----------------------------
@app.route("/extract_brand", methods=["POST"])
def extract_brand_route():
    _maybe_reload_config()
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")
    result = extract_brand(text)
    return jsonify(result)

@app.route("/reload", methods=["POST"])
def reload_route():
    global CONFIG
    CONFIG = _load_config()
    return jsonify({"ok": True, "reloaded": True})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "model": MODEL_NAME})

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    # e.g.:
    # curl -X POST localhost:8000/extract_brand -H "Content-Type: application/json" \
    #      -d '{"text":"battery life of galaxy fold 5"}'
    app.run(host="0.0.0.0", port=8000)

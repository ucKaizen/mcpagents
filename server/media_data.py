"""
AGF Germany-style TV audience measurement data engine.

All data is generated deterministically from seeds (hash-based) combined with
realistic demographic bias matrices. No database or static files needed —
same query always returns the same numbers.

Calibrated to real-world German TV audience ranges:
- Total TV universe: ~72M viewers (Germany 3+)
- Tagesschau reach: ~9M total
- Top prime-time share: 15-25%
- Channel shares: ARD ~12%, ZDF ~13%, RTL ~8%
"""

import hashlib
from typing import Optional

# ---------------------------------------------------------------------------
# Universe sizes by demographic (thousands) — approximate German population
# ---------------------------------------------------------------------------
UNIVERSE_TOTAL = 72_000  # thousands

UNIVERSE_BY_AGE = {
    "3-13":  7_200,
    "14-29": 12_600,
    "30-49": 19_800,
    "50-64": 16_200,
    "65+":   16_200,
}

UNIVERSE_BY_GENDER = {
    "Male":   35_300,
    "Female": 36_700,
}

# Rough splits: each age×gender cell
UNIVERSE_AGE_GENDER = {
    ("3-13",  "Male"):  3_700, ("3-13",  "Female"):  3_500,
    ("14-29", "Male"):  6_400, ("14-29", "Female"):  6_200,
    ("30-49", "Male"):  10_000,("30-49", "Female"):  9_800,
    ("50-64", "Male"):  7_900, ("50-64", "Female"):  8_300,
    ("65+",   "Male"):  7_300, ("65+",   "Female"):  8_900,
}

AGE_GROUPS = ["3-13", "14-29", "30-49", "50-64", "65+"]
GENDERS = ["Male", "Female"]

# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------
CHANNELS = {
    "Das Erste": {"type": "public", "group": "ARD", "description": "Flagship public channel of ARD, Germany's first public broadcaster"},
    "ZDF":       {"type": "public", "group": "ZDF", "description": "Zweites Deutsches Fernsehen, Germany's second public broadcaster"},
    "RTL":       {"type": "private", "group": "RTL Group", "description": "Largest German private broadcaster, entertainment and news"},
    "SAT.1":     {"type": "private", "group": "ProSiebenSat.1", "description": "Private channel known for shows, films, and magazines"},
    "ProSieben": {"type": "private", "group": "ProSiebenSat.1", "description": "Private channel targeting younger audiences, entertainment focus"},
    "VOX":       {"type": "private", "group": "RTL Group", "description": "Private channel with cooking shows, documentaries, and series"},
    "kabel eins":{"type": "private", "group": "ProSiebenSat.1", "description": "Private channel with classic series, films, and documentaries"},
    "RTL ZWEI":  {"type": "private", "group": "RTL Group", "description": "Private channel with reality TV and lifestyle formats"},
    "ARTE":      {"type": "public", "group": "ARTE", "description": "Franco-German cultural channel, documentaries and art-house films"},
    "3sat":      {"type": "public", "group": "ZDF/ARD/ORF/SRG", "description": "Public cultural and science channel, shared by German-speaking broadcasters"},
}

# ---------------------------------------------------------------------------
# Programs — each with base_reach (thousands) and base_share (%)
# ---------------------------------------------------------------------------
PROGRAMS = {
    # --- News ---
    "Tagesschau":           {"channel": "Das Erste", "genre": "News",          "timeslot": "20:00", "day": "daily",    "duration_min": 15,  "base_reach": 9200, "base_share": 28.0},
    "heute":                {"channel": "ZDF",       "genre": "News",          "timeslot": "19:00", "day": "daily",    "duration_min": 20,  "base_reach": 4100, "base_share": 18.0},
    "RTL aktuell":          {"channel": "RTL",       "genre": "News",          "timeslot": "18:45", "day": "daily",    "duration_min": 20,  "base_reach": 3200, "base_share": 14.5},
    "heute-journal":        {"channel": "ZDF",       "genre": "News",          "timeslot": "21:45", "day": "daily",    "duration_min": 30,  "base_reach": 4000, "base_share": 16.0},

    # --- Crime / Drama ---
    "Tatort":               {"channel": "Das Erste", "genre": "Crime",         "timeslot": "20:15", "day": "Sunday",   "duration_min": 90,  "base_reach": 8500, "base_share": 24.0},
    "SOKO Leipzig":         {"channel": "ZDF",       "genre": "Crime",         "timeslot": "21:15", "day": "Friday",   "duration_min": 45,  "base_reach": 4800, "base_share": 16.5},
    "Alarm fuer Cobra 11":  {"channel": "RTL",       "genre": "Crime",         "timeslot": "20:15", "day": "Thursday", "duration_min": 45,  "base_reach": 2800, "base_share": 9.5},
    "Der Alte":             {"channel": "ZDF",       "genre": "Crime",         "timeslot": "20:15", "day": "Friday",   "duration_min": 60,  "base_reach": 5200, "base_share": 18.0},

    # --- Entertainment ---
    "Wer wird Millionaer":  {"channel": "RTL",       "genre": "Entertainment", "timeslot": "20:15", "day": "Monday",   "duration_min": 60,  "base_reach": 3800, "base_share": 13.0},
    "Germanys Next Topmodel":{"channel": "ProSieben","genre": "Entertainment", "timeslot": "20:15", "day": "Thursday", "duration_min": 120, "base_reach": 2200, "base_share": 9.0},
    "The Voice of Germany": {"channel": "SAT.1",     "genre": "Entertainment", "timeslot": "20:15", "day": "Friday",   "duration_min": 120, "base_reach": 2500, "base_share": 10.0},
    "Schlag den Star":      {"channel": "ProSieben", "genre": "Entertainment", "timeslot": "20:15", "day": "Saturday", "duration_min": 180, "base_reach": 1800, "base_share": 7.5},
    "Let's Dance":          {"channel": "RTL",       "genre": "Entertainment", "timeslot": "20:15", "day": "Friday",   "duration_min": 150, "base_reach": 3500, "base_share": 14.0},

    # --- Sports ---
    "Sportschau":           {"channel": "Das Erste", "genre": "Sports",        "timeslot": "18:30", "day": "Saturday", "duration_min": 60,  "base_reach": 5500, "base_share": 22.0},
    "ran Fussball":         {"channel": "SAT.1",     "genre": "Sports",        "timeslot": "20:15", "day": "varies",   "duration_min": 120, "base_reach": 4200, "base_share": 16.0},

    # --- Soap / Daily ---
    "GZSZ":                 {"channel": "RTL",       "genre": "Soap",          "timeslot": "19:40", "day": "daily",    "duration_min": 25,  "base_reach": 2600, "base_share": 11.5},
    "Rote Rosen":           {"channel": "Das Erste", "genre": "Soap",          "timeslot": "14:10", "day": "daily",    "duration_min": 50,  "base_reach": 1600, "base_share": 12.0},
    "Sturm der Liebe":      {"channel": "Das Erste", "genre": "Soap",          "timeslot": "15:10", "day": "daily",    "duration_min": 50,  "base_reach": 1500, "base_share": 11.0},

    # --- Documentary ---
    "Terra X":              {"channel": "ZDF",       "genre": "Documentary",   "timeslot": "19:30", "day": "Sunday",   "duration_min": 45,  "base_reach": 4500, "base_share": 14.0},
    "Kulturzeit":           {"channel": "3sat",      "genre": "Documentary",   "timeslot": "19:20", "day": "daily",    "duration_min": 40,  "base_reach": 800,  "base_share": 3.0},
    "planet e":             {"channel": "ZDF",       "genre": "Documentary",   "timeslot": "16:30", "day": "Sunday",   "duration_min": 30,  "base_reach": 1800, "base_share": 10.0},

    # --- Talk ---
    "Maischberger":         {"channel": "Das Erste", "genre": "Talk",          "timeslot": "22:50", "day": "Wednesday","duration_min": 75,  "base_reach": 2200, "base_share": 12.5},
    "Markus Lanz":          {"channel": "ZDF",       "genre": "Talk",          "timeslot": "23:15", "day": "Tue-Thu",  "duration_min": 75,  "base_reach": 2000, "base_share": 14.0},

    # --- Reality ---
    "Das Dschungelcamp":    {"channel": "RTL",       "genre": "Reality",       "timeslot": "22:15", "day": "daily-event","duration_min": 90,"base_reach": 4000, "base_share": 18.0},
    "Die Hoehle der Loewen":{"channel": "VOX",       "genre": "Reality",       "timeslot": "20:15", "day": "Monday",   "duration_min": 120, "base_reach": 2400, "base_share": 10.0},

    # --- Film ---
    "Der Fernsehfilm der Woche":{"channel": "ZDF",   "genre": "Film",          "timeslot": "20:15", "day": "Monday",   "duration_min": 90,  "base_reach": 5000, "base_share": 16.5},
}

# ---------------------------------------------------------------------------
# Genres list (derived)
# ---------------------------------------------------------------------------
GENRES = sorted(set(p["genre"] for p in PROGRAMS.values()))

# ---------------------------------------------------------------------------
# Demographic bias matrices
# ---------------------------------------------------------------------------

GENRE_AGE_BIAS = {
    "News":          {"3-13": 0.05, "14-29": 0.25, "30-49": 0.70, "50-64": 1.40, "65+": 1.90},
    "Crime":         {"3-13": 0.05, "14-29": 0.20, "30-49": 0.65, "50-64": 1.35, "65+": 2.00},
    "Entertainment": {"3-13": 0.40, "14-29": 1.50, "30-49": 1.20, "50-64": 0.80, "65+": 0.50},
    "Sports":        {"3-13": 0.25, "14-29": 1.00, "30-49": 1.35, "50-64": 1.20, "65+": 0.85},
    "Soap":          {"3-13": 0.15, "14-29": 0.60, "30-49": 0.90, "50-64": 1.40, "65+": 1.70},
    "Documentary":   {"3-13": 0.08, "14-29": 0.30, "30-49": 0.80, "50-64": 1.35, "65+": 1.75},
    "Talk":          {"3-13": 0.02, "14-29": 0.20, "30-49": 0.70, "50-64": 1.40, "65+": 1.90},
    "Reality":       {"3-13": 0.30, "14-29": 1.60, "30-49": 1.30, "50-64": 0.70, "65+": 0.35},
    "Film":          {"3-13": 0.20, "14-29": 0.50, "30-49": 0.90, "50-64": 1.30, "65+": 1.50},
}

GENRE_GENDER_BIAS = {
    "News":          {"Male": 1.10, "Female": 0.90},
    "Crime":         {"Male": 0.95, "Female": 1.05},
    "Entertainment": {"Male": 0.70, "Female": 1.30},
    "Sports":        {"Male": 1.45, "Female": 0.55},
    "Soap":          {"Male": 0.45, "Female": 1.55},
    "Documentary":   {"Male": 1.15, "Female": 0.85},
    "Talk":          {"Male": 1.00, "Female": 1.00},
    "Reality":       {"Male": 0.65, "Female": 1.35},
    "Film":          {"Male": 1.05, "Female": 0.95},
}

# Channel-level age overlay (multiplicative on top of genre bias)
CHANNEL_AGE_BIAS = {
    "Das Erste": {"3-13": 0.80, "14-29": 0.70, "30-49": 0.90, "50-64": 1.15, "65+": 1.25},
    "ZDF":       {"3-13": 0.75, "14-29": 0.65, "30-49": 0.85, "50-64": 1.20, "65+": 1.30},
    "RTL":       {"3-13": 1.10, "14-29": 1.20, "30-49": 1.15, "50-64": 0.90, "65+": 0.75},
    "SAT.1":     {"3-13": 1.05, "14-29": 1.15, "30-49": 1.10, "50-64": 0.95, "65+": 0.80},
    "ProSieben": {"3-13": 1.20, "14-29": 1.50, "30-49": 1.10, "50-64": 0.70, "65+": 0.40},
    "VOX":       {"3-13": 0.90, "14-29": 1.10, "30-49": 1.15, "50-64": 1.00, "65+": 0.85},
    "kabel eins":{"3-13": 0.95, "14-29": 1.10, "30-49": 1.15, "50-64": 0.95, "65+": 0.80},
    "RTL ZWEI":  {"3-13": 1.10, "14-29": 1.40, "30-49": 1.15, "50-64": 0.75, "65+": 0.45},
    "ARTE":      {"3-13": 0.30, "14-29": 0.50, "30-49": 0.90, "50-64": 1.30, "65+": 1.50},
    "3sat":      {"3-13": 0.25, "14-29": 0.40, "30-49": 0.80, "50-64": 1.35, "65+": 1.60},
}

# Streaming skew — younger demos stream more, older less
STREAMING_AGE_MULTIPLIER = {
    "3-13":  0.60,
    "14-29": 1.80,
    "30-49": 1.20,
    "50-64": 0.50,
    "65+":   0.15,
}

STREAMING_BASE_FRACTION = 0.12  # streaming adds ~12% of linear reach on average


# ---------------------------------------------------------------------------
# Deterministic seed helper
# ---------------------------------------------------------------------------

def _seed(*parts) -> float:
    """Hash arbitrary inputs to a deterministic float in [0, 1)."""
    key = "|".join(str(p) for p in parts).lower()
    h = hashlib.md5(key.encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _jitter(seed_val: float, low: float = 0.88, high: float = 1.12) -> float:
    """Map a 0-1 seed to a jitter multiplier in [low, high]."""
    return low + seed_val * (high - low)


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def _get_universe(age_group: Optional[str], gender: Optional[str]) -> float:
    """Return universe size in thousands for the given demographic slice."""
    if age_group and gender:
        return UNIVERSE_AGE_GENDER.get((age_group, gender), 5_000)
    elif age_group:
        return UNIVERSE_BY_AGE.get(age_group, 10_000)
    elif gender:
        return UNIVERSE_BY_GENDER.get(gender, 36_000)
    else:
        return UNIVERSE_TOTAL


def _demo_multiplier(genre: str, channel: str, age_group: Optional[str], gender: Optional[str]) -> float:
    """Combined demographic multiplier from genre + channel biases."""
    m = 1.0
    if age_group:
        m *= GENRE_AGE_BIAS.get(genre, {}).get(age_group, 1.0)
        m *= CHANNEL_AGE_BIAS.get(channel, {}).get(age_group, 1.0)
    if gender:
        m *= GENRE_GENDER_BIAS.get(genre, {}).get(gender, 1.0)
    return m


def compute_reach(program_name: str, age_group: Optional[str] = None,
                  gender: Optional[str] = None) -> dict:
    """Compute reach metrics for a program + demographic slice."""
    prog = PROGRAMS.get(program_name)
    if not prog:
        return {"error": f"Program '{program_name}' not found"}

    base = prog["base_reach"]
    genre = prog["genre"]
    channel = prog["channel"]

    demo_mult = _demo_multiplier(genre, channel, age_group, gender)
    jit = _jitter(_seed("reach", program_name, age_group, gender))

    # For demographic subgroups, scale by that group's share of the universe
    universe = _get_universe(age_group, gender)
    universe_fraction = universe / UNIVERSE_TOTAL

    reach_k = base * demo_mult * universe_fraction * jit
    reach_k = round(max(reach_k, 1), 0)
    reach_pct = round(reach_k / universe * 100, 2)

    avg_viewing = prog["duration_min"] * (0.55 + 0.35 * _seed("view", program_name, age_group, gender))
    # Older demos watch longer
    if age_group in ("50-64", "65+"):
        avg_viewing *= 1.15
    elif age_group in ("3-13", "14-29"):
        avg_viewing *= 0.80

    return {
        "program": program_name,
        "channel": channel,
        "genre": genre,
        "age_group": age_group or "Total",
        "gender": gender or "Total",
        "reach_thousands": int(reach_k),
        "reach_percent": reach_pct,
        "avg_viewing_minutes": round(avg_viewing, 1),
    }


def compute_share(entity_name: str, entity_type: str = "channel",
                  age_group: Optional[str] = None, gender: Optional[str] = None) -> dict:
    """Compute market share for a channel or program."""
    if entity_type == "channel":
        ch = CHANNELS.get(entity_name)
        if not ch:
            return {"error": f"Channel '{entity_name}' not found"}
        # Aggregate: average share of programs on this channel
        ch_progs = {k: v for k, v in PROGRAMS.items() if v["channel"] == entity_name}
        if not ch_progs:
            return {"error": f"No programs found for channel '{entity_name}'"}
        shares = []
        for pname, pdata in ch_progs.items():
            demo_mult = _demo_multiplier(pdata["genre"], entity_name, age_group, gender)
            jit = _jitter(_seed("share", pname, age_group, gender))
            shares.append(pdata["base_share"] * demo_mult * jit)
        avg_share = sum(shares) / len(shares)
        return {
            "channel": entity_name,
            "type": ch["type"],
            "age_group": age_group or "Total",
            "gender": gender or "Total",
            "market_share_percent": round(avg_share, 2),
            "based_on_programs": len(ch_progs),
        }
    else:
        prog = PROGRAMS.get(entity_name)
        if not prog:
            return {"error": f"Program '{entity_name}' not found"}
        demo_mult = _demo_multiplier(prog["genre"], prog["channel"], age_group, gender)
        jit = _jitter(_seed("share", entity_name, age_group, gender))
        share = prog["base_share"] * demo_mult * jit
        return {
            "program": entity_name,
            "channel": prog["channel"],
            "age_group": age_group or "Total",
            "gender": gender or "Total",
            "market_share_percent": round(share, 2),
        }


def compute_genre_performance(genre: str, age_group: Optional[str] = None,
                              gender: Optional[str] = None) -> dict:
    """Aggregate reach and share for all programs in a genre."""
    genre_progs = {k: v for k, v in PROGRAMS.items() if v["genre"] == genre}
    if not genre_progs:
        return {"error": f"Genre '{genre}' not found. Available: {GENRES}"}

    results = []
    for pname in genre_progs:
        r = compute_reach(pname, age_group, gender)
        s = compute_share(pname, "program", age_group, gender)
        results.append({
            "program": pname,
            "channel": genre_progs[pname]["channel"],
            "reach_thousands": r["reach_thousands"],
            "reach_percent": r["reach_percent"],
            "market_share_percent": s["market_share_percent"],
        })

    total_reach = sum(r["reach_thousands"] for r in results)
    avg_share = sum(r["market_share_percent"] for r in results) / len(results)

    return {
        "genre": genre,
        "age_group": age_group or "Total",
        "gender": gender or "Total",
        "program_count": len(results),
        "total_reach_thousands": total_reach,
        "average_share_percent": round(avg_share, 2),
        "programs": results,
    }


def compute_top_programs(metric: str = "reach", n: int = 10,
                         age_group: Optional[str] = None,
                         gender: Optional[str] = None) -> list:
    """Return top N programs ranked by reach or share."""
    rows = []
    for pname in PROGRAMS:
        r = compute_reach(pname, age_group, gender)
        s = compute_share(pname, "program", age_group, gender)
        rows.append({
            "program": pname,
            "channel": PROGRAMS[pname]["channel"],
            "genre": PROGRAMS[pname]["genre"],
            "reach_thousands": r["reach_thousands"],
            "reach_percent": r["reach_percent"],
            "market_share_percent": s["market_share_percent"],
        })

    sort_key = "reach_thousands" if metric == "reach" else "market_share_percent"
    rows.sort(key=lambda x: x[sort_key], reverse=True)
    return rows[:n]


def compute_demographic_breakdown(entity_name: str, entity_type: str = "program") -> dict:
    """Full age_group x gender matrix for a program or channel."""
    if entity_type == "program" and entity_name not in PROGRAMS:
        return {"error": f"Program '{entity_name}' not found"}
    if entity_type == "channel" and entity_name not in CHANNELS:
        return {"error": f"Channel '{entity_name}' not found"}

    matrix = []
    for ag in AGE_GROUPS:
        for g in GENDERS:
            if entity_type == "program":
                r = compute_reach(entity_name, ag, g)
                s = compute_share(entity_name, "program", ag, g)
                matrix.append({
                    "age_group": ag,
                    "gender": g,
                    "reach_thousands": r["reach_thousands"],
                    "reach_percent": r["reach_percent"],
                    "market_share_percent": s["market_share_percent"],
                    "avg_viewing_minutes": r["avg_viewing_minutes"],
                })
            else:
                s = compute_share(entity_name, "channel", ag, g)
                matrix.append({
                    "age_group": ag,
                    "gender": g,
                    "market_share_percent": s["market_share_percent"],
                })

    return {
        "entity": entity_name,
        "entity_type": entity_type,
        "breakdown": matrix,
    }


def compute_cross_media(entity_name: str, entity_type: str = "program",
                        age_group: Optional[str] = None,
                        gender: Optional[str] = None) -> dict:
    """TV + streaming reach. Streaming skews younger."""
    if entity_type == "program":
        tv = compute_reach(entity_name, age_group, gender)
        if "error" in tv:
            return tv
        tv_reach = tv["reach_thousands"]
    else:
        # For channels, sum program reaches
        ch_progs = [k for k, v in PROGRAMS.items() if v["channel"] == entity_name]
        if not ch_progs:
            return {"error": f"Channel '{entity_name}' not found or has no programs"}
        tv_reach = sum(compute_reach(p, age_group, gender)["reach_thousands"] for p in ch_progs)

    # Streaming reach
    streaming_mult = STREAMING_BASE_FRACTION
    if age_group:
        streaming_mult *= STREAMING_AGE_MULTIPLIER.get(age_group, 1.0)
    jit = _jitter(_seed("stream", entity_name, age_group, gender), 0.80, 1.20)
    streaming_reach = int(round(tv_reach * streaming_mult * jit))

    # Total deduplicated (some overlap)
    overlap_fraction = 0.15 + 0.10 * _seed("overlap", entity_name, age_group, gender)
    overlap = int(round(streaming_reach * overlap_fraction))
    total_reach = tv_reach + streaming_reach - overlap

    universe = _get_universe(age_group, gender)

    return {
        "entity": entity_name,
        "entity_type": entity_type,
        "age_group": age_group or "Total",
        "gender": gender or "Total",
        "tv_reach_thousands": tv_reach,
        "streaming_reach_thousands": streaming_reach,
        "overlap_thousands": overlap,
        "total_reach_thousands": total_reach,
        "total_reach_percent": round(total_reach / universe * 100, 2),
    }

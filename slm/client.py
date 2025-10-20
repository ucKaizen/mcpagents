# client.py
# Standard lib only: csv, json, time, datetime, pathlib; plus requests
# pip install requests
import csv
import json
import time
import requests
from pathlib import Path
from datetime import datetime

ENDPOINT = "http://localhost:8000/extract_brand"
INPUT_CSV = Path("prompts.csv")
OUTPUT_CSV = Path("outputs.csv")
OUTPUT_JSONL = Path("outputs.jsonl")

SAMPLES = [
    {"id": "1", "timestamp": "2025-10-20T10:00:00Z", "text": "battery life of galaxy fold 5"},
    {"id": "2", "timestamp": "2025-10-20T10:05:00Z", "text": "lg tv features and specifications"},
    {"id": "3", "timestamp": "2025-10-20T10:10:00Z", "text": "compare iphone 15 pro vs pixel 9"},
]

def ensure_input_csv(path: Path) -> None:
    """Create prompts.csv with header + sample rows if it doesn't exist."""
    if path.exists():
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "timestamp", "text"])
        w.writeheader()
        for row in SAMPLES:
            w.writerow(row)
    print(f"Created sample input file: {path.resolve()}")

def call_service(text: str, retry: int = 2, backoff: float = 0.5) -> dict:
    """POST to the extract_brand service with light retries."""
    payload = {"text": text}
    for attempt in range(retry + 1):
        try:
            r = requests.post(ENDPOINT, json=payload, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < retry:
                time.sleep(backoff * (2 ** attempt))
            else:
                return {"brand": None, "surface": None, "confidence": 0.0, "method": "error", "error": str(e)}

def main():
    ensure_input_csv(INPUT_CSV)

    # Prepare output writers
    out_csv_exists = OUTPUT_CSV.exists()
    csv_f = OUTPUT_CSV.open("a", newline="", encoding="utf-8")
    jsonl_f = OUTPUT_JSONL.open("a", encoding="utf-8")

    csv_fields = [
        "id", "timestamp", "text",
        "brand", "surface", "confidence", "method", "error"
    ]

    csv_writer = csv.DictWriter(csv_f, fieldnames=csv_fields)

    if not out_csv_exists:
        csv_writer.writeheader()

    # Process rows
    processed, errors = 0, 0
    with INPUT_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rid = (row.get("id") or "").strip() or str(processed + 1)
            ts = (row.get("timestamp") or "").strip() or datetime.utcnow().isoformat() + "Z"
            text = (row.get("text") or "").strip()

            result = call_service(text)

            # Build a flat record for CSV
            record = {
                "id": rid,
                "timestamp": ts,
                "text": text,
                "brand": result.get("brand"),
                "surface": result.get("surface"),
                "confidence": result.get("confidence"),
                "method": result.get("method"),
                "error": result.get("error"),
            }
            csv_writer.writerow(record)

            # Also store full raw result in JSONL (including id/timestamp/text)
            full = {"id": rid, "timestamp": ts, "text": text, "result": result}
            jsonl_f.write(json.dumps(full, ensure_ascii=False) + "\n")

            processed += 1
            if result.get("error"):
                errors += 1

    csv_f.close()
    jsonl_f.close()

    print(f"Done. Processed: {processed}, errors: {errors}")
    print(f"- Input:  {INPUT_CSV.resolve()}")
    print(f"- Output: {OUTPUT_CSV.resolve()}")
    print(f"- Output: {OUTPUT_JSONL.resolve()}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""משיכת METAR/TAF מרשות שדות התעופה וכתיבתם ל-data/weather.json.

אותו מקור בדיוק כמו הנוטאמים, רק עם msgType=Weather — האתר מחליף בין
השניים באותו מתג בצד הלקוח.

עמידות זהה לזו של משיכת הנוטאמים: כשל לא דורס את הקובץ הקיים אלא
מסמן אותו stale. דיווח מזג אוויר ישן שמוצג כישן עדיף על דף ריק,
ובוודאי עדיף על דיווח ישן שמוצג כעדכני.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import iaa  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "weather.json")

USER_AGENT = (
    "binyamin-airspace/1.0 (+https://github.com/nadaval56/airspace) "
    "static site data fetcher"
)
TIMEOUT = 45

# תחנות שרלוונטיות לאזור. אין סינון בפועל — זה רק לתצוגה ולמיון.
NEARBY = ("LLBG", "LLJR", "LLIB", "LLHA", "LLRD", "LLHZ", "LLES", "LLSD")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fetch_page(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html",
            "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return iaa.decode(resp.read())


def load_existing() -> dict | None:
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="לא כותב לקובץ")
    ap.add_argument("--input", help="פרסור קובץ HTML מקומי במקום משיכה")
    args = ap.parse_args()

    existing = load_existing()
    timestamp = now_iso()

    try:
        if args.input:
            with open(args.input, "rb") as fh:
                page = iaa.decode(fh.read())
        else:
            print(f"משיכה מ-{iaa.WEATHER_URL}", file=sys.stderr)
            page = fetch_page(iaa.WEATHER_URL)
        reports = iaa.parse_weather_page(page)
        error = None
    except Exception as exc:
        reports, error = [], f"{type(exc).__name__}: {exc}"[:300]

    if not reports:
        # אותו עיקרון כמו בנוטאמים: אפס דיווחים אינו "מזג אוויר תקין",
        # אלא סימן שהמשיכה נשברה. שומרים את הקיים ומסמנים.
        message = error or "המקור הוחזר בלי דיווחים"
        print(f"אין דיווחים — {message}", file=sys.stderr)
        payload = dict(existing) if existing else {
            "generated_at": timestamp, "last_success": None,
            "source": iaa.WEATHER_URL, "reports": [],
        }
        payload["generated_at"] = timestamp
        payload["stale"] = True
        payload["last_error"] = {"at": timestamp, "message": message}
    else:
        by_kind: dict[str, int] = {}
        for report in reports:
            key = report.get("kind") or "אחר"
            by_kind[key] = by_kind.get(key, 0) + 1
        payload = {
            "generated_at": timestamp,
            "last_success": timestamp,
            "last_error": (existing or {}).get("last_error"),
            "stale": False,
            "source": iaa.WEATHER_URL,
            "source_name": "רשות שדות התעופה",
            "nearby": list(NEARBY),
            "counts": {"total": len(reports), **by_kind},
            "reports": reports,
        }
        print(f"{len(reports)} דיווחים: {by_kind}", file=sys.stderr)

    if args.dry_run:
        print("--dry-run: לא נכתב קובץ.", file=sys.stderr)
        return 0

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"נכתב {OUTPUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

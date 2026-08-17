#!/usr/bin/env python3
"""חילוץ פרקי ד', ה' ו-ו' של הפמ"ת ל-data/aip-aerodromes.geojson.

שדות תעופה, מנחתים ומשטחי נחיתה למסוקים — נקודה לכל שדה, עם שם, קוד
ICAO, גובה, וסוג שנגזר מהפרק שבו הוא יושב. ראו ההסבר המלא
ב-scripts/aip_aerodromes.py.

## למה זה מאמת את עצמו

כל אחד משלושת הפרקים נפתח בדף תוכן שמונה במפורש את מה שבתוכו:

    פרק ד' – שדות תעופה
    שדות התעופה הכלולים בפרק זה הינם:
    -הרצליה
    -חיפה
    -ראש פינה

הסקריפט קורא את הרשימה הזאת, ואז דורש למצוא פרק לכל שם שבה. שדה
שהרשימה מבטיחה ולא נמצא, או נמצא בלי נ"צ, **מדווח כאזהרה** ואינו
מנוחש — נקודה שגויה על מפה תעופתית גרועה מנקודה חסרה.

שימוש:
    python3 scripts/build_aerodromes.py                 # מוריד מה-Release
    python3 scripts/build_aerodromes.py --pdf a.pdf     # מקובץ מקומי
    python3 scripts/build_aerodromes.py --cache p.json  # מקובץ שורות שכבר חולץ
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aip_aerodromes as fields  # noqa: E402
from aip_annexes import _unmirror_line, reverse_hebrew  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "aip-aerodromes.geojson")

SOURCE_URL = "https://github.com/nadaval56/airspace/releases/download/aip-source/pamat.pdf"

SOURCE_LABELS = {
    "airport": 'פמ"ת, פרק ד\' — שדות תעופה',
    "airstrip": 'פמ"ת, פרק ה\' — מנחתים',
    "agricultural": 'פמ"ת, פרק ה\' — מנחתים נוספים',
    "helipad": 'פמ"ת, פרק ו\' — משטחי נחיתה למסוקים',
}

# שם הפרק של טבלת המנחתים החקלאיים, כפי שהוא בכותרת הרצה.
AGRICULTURAL_CHAPTER = "מנחתים נוספים"

# עמוד נספח נושא את שם השדה ועוד "נספח א'" — אותו שדה, לא שדה אחר.
_ANNEX_SUFFIX_RE = re.compile(r"\s*נספח.*$")


def load_pdf(path: str | None):
    import pdfplumber

    if path:
        return pdfplumber.open(path)
    print(f"מוריד {SOURCE_URL}", file=sys.stderr)
    request = urllib.request.Request(
        SOURCE_URL, headers={"User-Agent": "binyamin-airspace/1.0"}
    )
    with urllib.request.urlopen(request, timeout=900) as resp:
        blob = resp.read()
    print(f"  {len(blob):,} bytes", file=sys.stderr)
    return pdfplumber.open(io.BytesIO(blob))


def page_lines(pdf) -> list[list[str]]:
    """שורות מיושרות לכל עמוד. זה השלב האיטי — 440 עמודים."""
    out = []
    for number, page in enumerate(pdf.pages, 1):
        text = page.extract_text() or ""
        out.append([_unmirror_line(line) for line in text.split("\n") if line.strip()])
        if number % 50 == 0:
            print(f"  {number} עמודים", file=sys.stderr)
    return out


# ---------------------------------------------------------------------------
# מבנה המסמך
# ---------------------------------------------------------------------------

_LIST_ITEM_RE = re.compile(r"^-\s*(?P<name>.+?)\s*$")


def volume_starts(pages: list[list[str]]) -> list[tuple[int, str]]:
    """[(אינדקס העמוד, מפתח הפרק)] לפי דפי התוכן של הפרקים."""
    found = []
    for index, lines in enumerate(pages):
        for line in lines:
            key = fields.volume_of(line)
            if key:
                found.append((index, key))
                break
    return found


def expected_names(lines: list[str]) -> list[str]:
    """השמות שדף התוכן של הפרק מבטיח."""
    names = []
    for line in lines:
        match = _LIST_ITEM_RE.match(line)
        if match:
            name = match.group("name").strip()
            if name and "פרק" not in name:
                names.append(name)
    return names


def normalise(name: str) -> str:
    """שם להשוואה: בלי סיומת נספח, בלי מקפים וגרשיים, רווח אחד."""
    text = _ANNEX_SUFFIX_RE.sub("", name)
    text = re.sub(r"[\"'’״׳()]", "", text)
    text = re.sub(r"[-–]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def group_pages(pages: list[list[str]], start: int, stop: int) -> dict[str, dict]:
    """מקבץ את עמודי הפרק לשדות, לפי שם שבכותרת הרצה.

    עמוד תרשים אינו נושא כותרת רצה, אבל הוא **בא אחרי** עמודי המלל של
    אותו שדה — ולכן הוא נצמד לשדה האחרון שנראה. הוא נשמר בנפרד
    (`chart_lines`): הטקסט העברי בעמודי התרשים יוצא מגופן סימבולי
    ומגיע כג'יבריש, ורק הלטינית שבו — 'ELEV 884 ft' — קריאה.
    """
    groups: dict[str, dict] = {}
    current: dict | None = None
    for index in range(start, stop):
        name = None
        for line in pages[index][:3]:
            name = fields.running_head(line)
            if name:
                break
        if name:
            key = normalise(name)
            current = groups.setdefault(
                key,
                {
                    "name": _ANNEX_SUFFIX_RE.sub("", name).strip(),
                    "pages": [],
                    "lines": [],
                    "chart_lines": [],
                },
            )
            current["pages"].append(index + 1)
            current["lines"].extend(pages[index])
        elif current is not None:
            current["chart_lines"].extend(pages[index])
    return groups


def extract(pdf, pages: list[list[str]]) -> tuple[list[dict], list[str]]:
    starts = volume_starts(pages)
    warnings: list[str] = []
    records: list[dict] = []

    missing_volumes = [key for key, _, _ in fields.VOLUMES
                       if key not in {k for _, k in starts}]
    if missing_volumes:
        raise SystemExit(
            "לא אותרו דפי התוכן של הפרקים: "
            + ", ".join(fields.VOLUME_LABELS[k] for k in missing_volumes)
            + " — מבנה המסמך השתנה?"
        )

    bounds = [index for index, _ in starts] + [len(pages)]

    for position, (start, key) in enumerate(starts):
        stop = bounds[position + 1]
        promised = expected_names(pages[start])
        groups = group_pages(pages, start + 1, stop)
        print(
            f"  {fields.VOLUME_LABELS[key]}: עמודים {start + 1}-{stop}, "
            f"{len(promised)} ברשימה, {len(groups)} פרקים",
            file=sys.stderr,
        )

        for name, entry in groups.items():
            if name == normalise(AGRICULTURAL_CHAPTER):
                records.extend(agricultural(pdf, entry, warnings))
                continue
            surfaces, notes = fields.parse_field(
                entry["name"], entry["lines"], key, entry["pages"],
                chart_lines=entry.get("chart_lines"),
            )
            warnings.extend(notes)
            if not surfaces:
                warnings.append(
                    f"{entry['name']}: לא נמצאה נקודת ציון מרכזית קריאה — דולג."
                )
                continue
            for record in surfaces:
                if not fields.in_israel(record["lat"], record["lon"]):
                    warnings.append(
                        f"{record['name']}: נ\"צ מחוץ לתיבת ישראל "
                        f"({record['lat']}, {record['lon']}) — דולג."
                    )
                    continue
                records.append(record)

        # דף התוכן הוא ההבטחה, והשוואה אליו היא הבדיקה. ההשוואה היא על
        # השם הבסיסי: פרק עם שני משטחים מפיק "ראשון לציון — מנחת מז\"מ",
        # ומי שמשווה את המלא מדווח על חוסר שאינו קיים.
        seen = {normalise(r["name"].split(" — ")[0]) for r in records}
        for promise in promised:
            if normalise(promise) not in seen and promise != AGRICULTURAL_CHAPTER:
                warnings.append(
                    f'{fields.VOLUME_LABELS[key]}: "{promise}" מופיע ברשימת הפרק ולא חולץ.'
                )

    return records, warnings


def agricultural(pdf, entry: dict, warnings: list[str]) -> list[dict]:
    """המנחתים החקלאיים — טבלה, ולכן נקראת כטבלה ולא כטקסט.

    כל תא מיושר ב-`reverse_hebrew` ולא ב-`_unmirror_line`: תא בטבלה
    נשבר לכמה שורות, וההיפוך של המחרוזת כולה מזיז את השורה השנייה לפני
    הראשונה — "רשות החולה" נקרא "החולה רשות", ו"אליעז )חפציבה(" נקרא
    "(חפציבה) אליעז". פירוק לשורות שומר את סדרן.
    """
    rows: list[list[str]] = []
    for number in entry["pages"]:
        for table in pdf.pages[number - 1].extract_tables():
            for row in table:
                rows.append([reverse_hebrew(cell or "") for cell in row])
    parsed, notes = fields.parse_agricultural(rows)
    warnings.extend(notes)
    print(f"    מנחתים חקלאיים: {len(parsed)}", file=sys.stderr)
    return parsed


# ---------------------------------------------------------------------------
# פלט
# ---------------------------------------------------------------------------


def slug(record: dict) -> str:
    """מזהה ייחוד לשדה. משטח שני באותו פרק מקבל סיומת מהשם שבמקור."""
    base = record["icao"] or re.sub(r"\s+", "-", normalise(record["name"]))
    surface = record.get("surface")
    if surface and record["icao"]:
        return f"{base}-{re.sub(r'[^א-ת]+', '-', surface).strip('-')}"
    return base


def feature(record: dict) -> dict:
    properties = {
        "id": slug(record),
        "name": record["name"],
        "kind": record["kind"],
        "kind_label": fields.VOLUME_LABELS[record["kind"]],
        "source": SOURCE_LABELS[record["kind"]],
    }
    for key in ("title", "icao", "elevation_ft", "atz_radius_nm", "operator",
                "contact", "note"):
        value = record.get(key)
        if value not in (None, ""):
            properties[key] = value
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [record["lon"], record["lat"]]},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", help="קובץ מקומי במקום הורדה")
    parser.add_argument("--cache", help="קובץ JSON של שורות עמודים, לפיתוח")
    parser.add_argument("--dry-run", action="store_true", help="לא כותב לקובץ")
    args = parser.parse_args()

    pdf = load_pdf(args.pdf)
    if args.cache and os.path.exists(args.cache):
        with open(args.cache, encoding="utf-8") as fh:
            pages = json.load(fh)
        print(f"{len(pages)} עמודים מהמטמון {args.cache}", file=sys.stderr)
    else:
        pages = page_lines(pdf)
        if args.cache:
            with open(args.cache, "w", encoding="utf-8") as fh:
                json.dump(pages, fh, ensure_ascii=False)

    records, warnings = extract(pdf, pages)
    for warning in warnings:
        print(f"אזהרה: {warning}", file=sys.stderr)

    counts: dict[str, int] = {}
    for record in records:
        counts[record["kind"]] = counts.get(record["kind"], 0) + 1
    print(
        "סה\"כ: " + ", ".join(
            f"{fields.VOLUME_LABELS[k]} {v}" for k, v in sorted(counts.items())
        ),
        file=sys.stderr,
    )

    payload = {
        "type": "FeatureCollection",
        "metadata": {
            "title": 'שדות תעופה, מנחתים ומשטחי מסוקים — פמ"ת פרקים ד\', ה\' ו-ו\'',
            "source_pdf": SOURCE_URL,
            "extracted_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "counts": counts,
            "geometry_note": (
                "נקודה אחת לכל שדה — נקודת הציון המרכזית (ARP) שבפרק. אזור "
                "השדה (ATZ) מתואר בפמ\"ת במילים ולא בקואורדינטות, ולכן אינו "
                "מצויר; רדיוס שכתוב במפורש נשמר בשדה atz_radius_nm."
            ),
            "warnings": warnings,
        },
        "features": [feature(record) for record in sorted(records, key=slug)],
    }

    if args.dry_run:
        print(json.dumps(payload["metadata"], ensure_ascii=False, indent=1))
        for f in payload["features"]:
            print(json.dumps(f["properties"], ensure_ascii=False))
        return 0

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    print(f"נכתב {OUTPUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

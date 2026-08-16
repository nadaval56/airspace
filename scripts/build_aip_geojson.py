#!/usr/bin/env python3
"""חילוץ נספחי ב' ו-ג' מפמ"ת פרק א-17 ל-GeoJSON.

עבודה חד־פעמית ברובה. השכבה הזאת חשובה יותר משכבת הנוטאמים — היא מדויקת,
יציבה ובשליטה מלאה — ולכן הסקריפט שמרני בכוונה: מה שלא חולץ בביטחון
מדווח ולא מנוחש. אזור מגבלה שגוי מסוכן יותר מאזור חסר.

שימוש:
    python3 scripts/build_aip_geojson.py --dump-text      # הדפסת טקסט ה-PDF לבדיקה
    python3 scripts/build_aip_geojson.py --dump-text --pages 40-60
    python3 scripts/build_aip_geojson.py                  # חילוץ וכתיבת GeoJSON
    python3 scripts/build_aip_geojson.py --pdf local.pdf  # מקובץ מקומי
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "aip-permanent.geojson")

AIP_URL = "https://www.gov.il/BlobFolder/guide/aip/he/aip_%D7%90'-17.pdf"

# חיתוך לתיבה של מטה בנימין. כל הארץ תהפוך את המפה לבלתי קריאה.
BBOX = {"min_lon": 35.0, "min_lat": 31.7, "max_lon": 35.4, "max_lat": 32.1}

USER_AGENT = "binyamin-airspace/1.0 (+https://github.com/nadaval56/airspace)"

# ---------------------------------------------------------------------------
# קואורדינטות
# ---------------------------------------------------------------------------
# הפמ"ת מנוסח בכמה וריאציות. מכסים DDMMSS ו-DDMM, עם ובלי סימני מעלות.

_LAT_LON_RE = re.compile(
    r"""
    (?P<lat_d>\d{2}) \s*[°\s]?\s*
    (?P<lat_m>\d{2}) \s*['′\s]?\s*
    (?:(?P<lat_s>\d{2}(?:\.\d+)?) \s*["″\s]?\s*)?
    (?P<ns>[NS]) \s*[,/]?\s*
    (?P<lon_d>\d{3}) \s*[°\s]?\s*
    (?P<lon_m>\d{2}) \s*['′\s]?\s*
    (?:(?P<lon_s>\d{2}(?:\.\d+)?) \s*["″\s]?\s*)?
    (?P<ew>[EW])
    """,
    re.X,
)

_CIRCLE_RE = re.compile(
    r"(?:circle|רדיוס|radius)[^\n]{0,60}?(\d+(?:\.\d+)?)\s*(NM|KM|מייל|ק\"מ)",
    re.I,
)


def parse_coordinates(text: str) -> list[tuple[float, float]]:
    """מלקט את כל צמדי הקואורדינטות בטקסט, לפי סדר הופעתם.

    מחזיר [(lon, lat), ...] — סדר GeoJSON.
    """
    points: list[tuple[float, float]] = []
    for m in _LAT_LON_RE.finditer(text):
        lat = int(m.group("lat_d")) + int(m.group("lat_m")) / 60.0
        if m.group("lat_s"):
            lat += float(m.group("lat_s")) / 3600.0
        lon = int(m.group("lon_d")) + int(m.group("lon_m")) / 60.0
        if m.group("lon_s"):
            lon += float(m.group("lon_s")) / 3600.0
        if m.group("ns") == "S":
            lat = -lat
        if m.group("ew") == "W":
            lon = -lon
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            points.append((round(lon, 6), round(lat, 6)))
    return points


def circle_to_polygon(lon: float, lat: float, radius_nm: float, steps: int = 64) -> list:
    """מקרב עיגול לפוליגון. GeoJSON לא יודע עיגולים."""
    radius_km = radius_nm * 1.852
    ring = []
    for i in range(steps + 1):
        bearing = 2 * math.pi * i / steps
        d = radius_km / 6371.0
        lat1, lon1 = math.radians(lat), math.radians(lon)
        lat2 = math.asin(
            math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(bearing)
        )
        lon2 = lon1 + math.atan2(
            math.sin(bearing) * math.sin(d) * math.cos(lat1),
            math.cos(d) - math.sin(lat1) * math.sin(lat2),
        )
        ring.append((round(math.degrees(lon2), 6), round(math.degrees(lat2), 6)))
    return [ring]


# ---------------------------------------------------------------------------
# סיווג אזורים
# ---------------------------------------------------------------------------

_DESIGNATOR_RE = re.compile(r"\bLL\s*[\(\-]?\s*([PRD])\s*[\)\-]?\s*[- ]?\s*(\d{1,3}[A-Z]?)\b")


def classify(designator: str, context: str) -> str:
    letter = ""
    m = _DESIGNATOR_RE.search(designator or "")
    if m:
        letter = m.group(1).upper()
    haystack = (designator or "") + " " + (context or "")
    if re.search(r"כטב|כטבם|UAV|RPAS|מזלט|רחפן", haystack, re.I):
        return "כטב\"ם"
    if letter == "P" or "אסור" in haystack:
        return "אסור"
    if letter == "R" or "מוגבל" in haystack:
        return "מוגבל"
    if letter == "D" or "מסוכן" in haystack:
        return "מסוכן"
    return "לא מסווג"


# ---------------------------------------------------------------------------
# חיתוך לתיבה
# ---------------------------------------------------------------------------


def intersects_bbox(coords: list) -> bool:
    """האם לפוליגון יש חפיפה כלשהי לתיבת מטה בנימין.

    בדיקת חפיפת מלבנים חוסמים — מספיקה כאן, ולא מסתכנת בקיצוץ גיאומטריה.
    פוליגון שנוגע בתיבה נשמר בשלמותו, לא נחתך.
    """
    lons = [pt[0] for ring in coords for pt in ring]
    lats = [pt[1] for ring in coords for pt in ring]
    if not lons or not lats:
        return False
    return not (
        max(lons) < BBOX["min_lon"]
        or min(lons) > BBOX["max_lon"]
        or max(lats) < BBOX["min_lat"]
        or min(lats) > BBOX["max_lat"]
    )


# ---------------------------------------------------------------------------
# קריאת ה-PDF
# ---------------------------------------------------------------------------


# gov.il מחזיר 404 לבקשות שלא נראות כמו דפדפן. הכותרות האלה נדרשות.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    "Referer": "https://www.gov.il/he/pages/aip",
}

AIP_INDEX_PAGES = [
    "https://www.gov.il/he/pages/aip",
    "https://www.gov.il/he/departments/guides/aip",
]


def _fetch(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers=_BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _url_variants(url: str) -> list[str]:
    """גרסאות קידוד שונות לאותה כתובת. הגרש בשם הקובץ הוא מקור צרות."""
    variants = [url]
    if "'" in url:
        variants.append(url.replace("'", "%27"))
    if "%27" in url:
        variants.append(url.replace("%27", "'"))
    if "%D7%90" in url:
        variants.append(url.replace("%D7%90", "א"))
    seen: list[str] = []
    for v in variants:
        if v not in seen:
            seen.append(v)
    return seen


def discover_pdf_url() -> str | None:
    """מאתר את הקישור ל-א-17 מתוך דף המדריך של הפמ"ת.

    נדרש כי שם הקובץ ב-gov.il השתנה בעבר. עדיף לגלות מהמקור מאשר לקבע.
    """
    for page in AIP_INDEX_PAGES:
        try:
            html = _fetch(page, timeout=60).decode("utf-8", errors="replace")
        except Exception as exc:
            print(f"  גילוי: {page} — {exc}", file=sys.stderr)
            continue
        links = re.findall(r"""["'(]([^"'()\s]*BlobFolder[^"'()\s]*\.pdf)""", html)
        print(f"  גילוי: {page} — {len(links)} קישורי PDF", file=sys.stderr)
        for link in links:
            decoded = urllib.parse.unquote(link)
            if re.search(r"א\s*'?\s*-?\s*17", decoded):
                full = link if link.startswith("http") else "https://www.gov.il" + link
                print(f"  נמצא: {full}", file=sys.stderr)
                return full
    return None


def download_pdf(url: str, dest: str) -> str:
    """מוריד את ה-PDF. מנסה וריאנטים של קידוד, ואז גילוי מדף המדריך."""
    attempts = _url_variants(url)
    for candidate in attempts:
        try:
            data = _fetch(candidate)
        except Exception as exc:
            print(f"  {getattr(exc, 'code', '')} {candidate} — {exc}", file=sys.stderr)
            continue
        if data[:4] != b"%PDF":
            print(f"  לא PDF ({len(data)} בתים): {candidate}", file=sys.stderr)
            continue
        with open(dest, "wb") as fh:
            fh.write(data)
        print(f"  הורד {len(data):,} בתים מ-{candidate}", file=sys.stderr)
        return dest

    print("הכתובת הישירה נכשלה — מנסה לגלות מדף המדריך.", file=sys.stderr)
    found = discover_pdf_url()
    if found:
        data = _fetch(found)
        if data[:4] == b"%PDF":
            with open(dest, "wb") as fh:
                fh.write(data)
            print(f"  הורד {len(data):,} בתים מ-{found}", file=sys.stderr)
            return dest

    raise RuntimeError(
        "לא הצלחתי להוריד את ה-PDF של הפמ\"ת. "
        "הורידו ידנית מ-https://www.gov.il/he/pages/aip והריצו עם --pdf."
    )


def pdf_pages(path: str) -> list[str]:
    """מחזיר טקסט לכל עמוד. דורש pdfplumber (ראו requirements.txt)."""
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        sys.exit("חסר pdfplumber. התקינו: pip install -r requirements.txt")

    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return pages


def parse_page_range(spec: str | None, total: int) -> range:
    if not spec:
        return range(total)
    m = re.match(r"^(\d+)(?:-(\d+))?$", spec.strip())
    if not m:
        sys.exit(f"טווח עמודים לא תקין: {spec!r}")
    start = int(m.group(1)) - 1
    end = int(m.group(2) or m.group(1))
    return range(max(0, start), min(total, end))


# ---------------------------------------------------------------------------
# חילוץ
# ---------------------------------------------------------------------------


def extract_features(pages: list[str], page_range: range) -> tuple[list[dict], list[str]]:
    """חילוץ אזורים. מחזיר (features, אזהרות).

    כל בלוק שמתחיל במזהה אזור (LL(P)-nn וכדומה) ונמשך עד המזהה הבא נחשב
    לרשומה אחת. בלוק עם פחות מ-3 נקודות ובלי הגדרת עיגול מדווח כאזהרה
    ולא נכנס לפלט — עדיף חוסר מאשר צורה מומצאת.
    """
    features: list[dict] = []
    warnings: list[str] = []

    text = "\n".join(pages[i] for i in page_range)
    matches = list(_DESIGNATOR_RE.finditer(text))
    if not matches:
        warnings.append(
            "לא נמצא אף מזהה אזור בתבנית LL(P/R/D)-nn. "
            "הריצו עם --dump-text כדי לראות את מבנה המסמך בפועל."
        )
        return features, warnings

    for idx, m in enumerate(matches):
        stop = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[m.start():stop]
        designator = f"LL({m.group(1).upper()})-{m.group(2)}"

        points = parse_coordinates(block)
        geometry = None

        circle = _CIRCLE_RE.search(block)
        if circle and len(points) >= 1:
            radius = float(circle.group(1))
            if circle.group(2).upper() in ("KM", 'ק"מ'):
                radius /= 1.852
            geometry = {
                "type": "Polygon",
                "coordinates": circle_to_polygon(points[0][0], points[0][1], radius),
            }
        elif len(points) >= 3:
            ring = list(points)
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            geometry = {"type": "Polygon", "coordinates": [ring]}
        else:
            warnings.append(
                f"{designator}: {len(points)} נקודות בלבד ואין הגדרת עיגול — דולג."
            )
            continue

        if not intersects_bbox(geometry["coordinates"]):
            continue

        features.append({
            "type": "Feature",
            "properties": {
                "id": designator,
                "name": _guess_name(block),
                "type": classify(designator, block),
                "lower_limit": _find_limit(block, lower=True),
                "upper_limit": _find_limit(block, lower=False),
                "notes": _tidy_block(block),
                "source": "פמ\"ת א-17",
            },
            "geometry": geometry,
        })

    return features, warnings


def _guess_name(block: str) -> str | None:
    for line in block.split("\n"):
        line = line.strip()
        # שורה עם מילים בעברית ובלי קואורדינטות — סביר שזה השם.
        if re.search(r"[֐-׿]{3,}", line) and not _LAT_LON_RE.search(line):
            return line[:120]
    return None


def _find_limit(block: str, lower: bool) -> str | None:
    pattern = (
        r"(SFC|GND|קרקע|\d{1,3},?\d{0,3}\s*(?:FT|רגל|M|מ')|FL\s*\d{2,3}|UNL|ללא הגבלה)"
    )
    found = re.findall(pattern, block, re.I)
    if not found:
        return None
    return found[0] if lower else found[-1]


def _tidy_block(block: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in block.split("\n")]
    return " | ".join(line for line in lines if line)[:600]


# ---------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", help="נתיב ל-PDF מקומי במקום הורדה")
    ap.add_argument("--url", default=AIP_URL, help="כתובת ה-PDF")
    ap.add_argument("--pages", help="טווח עמודים, למשל 40-60")
    ap.add_argument("--dump-text", action="store_true", help="הדפסת הטקסט ויציאה")
    ap.add_argument("--dry-run", action="store_true", help="לא כותב לקובץ")
    args = ap.parse_args()

    path = args.pdf
    if not path:
        path = os.path.join(REPO_ROOT, "aip-a17.pdf")
        print(f"מוריד {args.url}", file=sys.stderr)
        download_pdf(args.url, path)

    pages = pdf_pages(path)
    print(f"{len(pages)} עמודים ב-PDF", file=sys.stderr)
    page_range = parse_page_range(args.pages, len(pages))

    if args.dump_text:
        for i in page_range:
            print(f"\n{'=' * 70}\n=== עמוד {i + 1} ===\n{'=' * 70}")
            print(pages[i])
        return 0

    features, warnings = extract_features(pages, page_range)

    for w in warnings:
        print(f"אזהרה: {w}", file=sys.stderr)
    print(f"{len(features)} אזורים בתוך התיבה", file=sys.stderr)

    payload = {
        "type": "FeatureCollection",
        "metadata": {
            "title": "מגבלות קבועות — פמ\"ת פרק א-17, נספחים ב' ו-ג'",
            "source_pdf": args.url,
            "bbox": [BBOX["min_lon"], BBOX["min_lat"], BBOX["max_lon"], BBOX["max_lat"]],
            "extracted_at": now_iso(),
            "status": "ok" if features else "empty",
            "status_he": (
                f"{len(features)} אזורים חולצו מהנספחים."
                if features
                else "החילוץ לא הניב אזורים. ראו אזהרות ביומן הריצה."
            ),
            "warnings": warnings,
        },
        "features": features,
    }

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=1)[:4000])
        return 0

    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"נכתב {OUTPUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

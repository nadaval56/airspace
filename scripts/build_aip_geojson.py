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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aip_narrative  # noqa: E402
from aip_annexes import (  # noqa: E402
    BBOX,
    feature_extent,
    find_annex_pages,
    intersects_bbox,
    parse_annex_rows,
    reverse_hebrew,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "aip-permanent.geojson")

AIP_URL = "https://www.gov.il/BlobFolder/guide/aip/he/aip_%D7%90'-17.pdf"

# עותק ידני של ה-PDF, אם הונח במאגר. גובר על ההורדה מהרשת.
VENDORED_PDF = os.path.join(REPO_ROOT, "data", "aip-a17.pdf")


USER_AGENT = "binyamin-airspace/1.0 (+https://github.com/nadaval56/airspace)"


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
        # תווים לא-ASCII חייבים קידוד לפני שהם מגיעים ל-urllib, אחרת
        # הבקשה קורסת על 'ascii' codec ולא נבדקת כלל.
        variants.append(
            urllib.parse.quote(url.replace("%D7%90", "א"), safe=":/?&=%'")
        )
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


def pdf_from_zip() -> str | None:
    """מחלץ את א'-17 מארכיון הפמ"ת אם הוא נמצא במאגר.

    gov.il חוסם הורדה אוטומטית, אז הארכיון מגיע ידנית. קריאה ישירה
    ממנו חוסכת צעד נוסף.
    """
    import glob
    import zipfile

    for archive in sorted(glob.glob(os.path.join(REPO_ROOT, "*.zip"))):
        try:
            with zipfile.ZipFile(archive) as zf:
                members = [
                    n for n in zf.namelist()
                    if n.lower().endswith(".pdf") and "17" in n and "נספח" not in n
                ]
                if not members:
                    continue
                dest = os.path.join(REPO_ROOT, "aip-a17.pdf")
                with open(dest, "wb") as fh:
                    fh.write(zf.read(members[0]))
                print(f"חולץ {members[0]} מתוך {os.path.basename(archive)}", file=sys.stderr)
                return dest
        except zipfile.BadZipFile:
            continue
    return None


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


def read_narrative(pages: list[str], ranges: dict[str, tuple[int, int]]) -> dict[str, dict]:
    """מפרסר את מלל הפרק — כל מה שלפני הנספח הראשון.

    המלל אינו קישוט: הוא הפרסום הקובע במקרה של סתירה (כתוב בעמוד
    הראשון של הפרק), והוא אומר על אזורים דברים שהטבלה משמיטה — שמורת
    טבע, מכון מחקר, ומי גורם התיאום. ראו scripts/aip_narrative.py.
    """
    if not ranges:
        return {}
    body_end = min(start for start, _ in ranges.values())
    # היישור נעשה שורה־שורה: פריט ברשימה מזוהה לפי **תחילת השורה**,
    # ואיחוד שורות לפני הפרסור היה מוחק בדיוק את הסימן הזה.
    lines = [
        reverse_hebrew(raw)
        for text in pages[:body_end]
        for raw in text.split("\n")
    ]
    entries = aip_narrative.parse_body(lines)
    print(
        f"  מלל: עמודים 1-{body_end}, {len(entries)} אזורים, "
        f"{sum(1 for e in entries.values() if e['coordination'])} עם גורם תיאום",
        file=sys.stderr,
    )
    return entries


def extract_features(path: str, pages: list[str]) -> tuple[list[dict], list[str]]:
    """מחלץ את נספחים ב' ו-ג' וחותך לתיבת מטה בנימין.

    הטבלה נקראת דרך extract_tables ולא כטקסט שטוח — ראו ההסבר
    ב-scripts/aip_annexes.py.
    """
    import pdfplumber  # type: ignore

    ranges = find_annex_pages(pages)
    narrative = read_narrative(pages, ranges)
    features: list[dict] = []
    warnings: list[str] = []

    with pdfplumber.open(path) as pdf:
        for key, label in (("b", "נספח ב'"), ("c", "נספח ג'")):
            if key not in ranges:
                warnings.append(f"{label} לא אותר במסמך.")
                continue
            start, stop = ranges[key]
            rows: list[list] = []
            for page in pdf.pages[start:stop]:
                for table in page.extract_tables():
                    rows.extend(table)

            source = f"פמ\"ת א-17, {label}"
            found, warns = parse_annex_rows(rows, source, narrative)
            inside = [f for f in found if intersects_bbox(f)]
            print(
                f"  {label}: עמודים {start + 1}-{stop}, {len(rows)} שורות טבלה, "
                f"{len(found)} אזורים, {len(inside)} בתוך התיבה",
                file=sys.stderr,
            )
            features.extend(inside)
            warnings.extend(f"{label} — {w}" for w in warns)

    # בדיקת שפיות אחרונה: אזור מגבלה שנמתח על יותר ממעלה אחת (כ-110 ק"מ)
    # כמעט תמיד סימן לקיבוץ שגוי. מדווחים בקול ולא בולעים בשקט.
    for feature in features:
        width, height = feature_extent(feature)
        if width > 1.0 or height > 1.0:
            warnings.append(
                f"{feature['properties']['id']}: מידות חריגות "
                f"({width:.2f}° × {height:.2f}°) — בדקו מול המקור."
            )

    return features, warnings


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
        path = pdf_from_zip()
    if not path and os.path.exists(VENDORED_PDF):
        # gov.il חוסם הורדה אוטומטית (403 לדפים, 404 לקישור הישיר), אז
        # עותק שהונח ידנית במאגר הוא המסלול המהימן.
        path = VENDORED_PDF
        print(f"משתמש בעותק שבמאגר: {VENDORED_PDF}", file=sys.stderr)
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

    features, warnings = extract_features(path, pages)

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
        # דחוס, כמו שאר שכבות הגיאומטריה: `indent=1` הכפיל את הקובץ
        # שהדפדפן מוריד פי 2.2 (186KB → 411KB) בלי להוסיף שום נתון,
        # וזה קובץ שנטען בכל פתיחה של הדף בשדה.
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    print(f"נכתב {OUTPUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

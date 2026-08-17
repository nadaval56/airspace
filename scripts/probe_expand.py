#!/usr/bin/env python3
"""אבחון ממוקד: כפתור ההרחבה של רשות שדות התעופה.

דף הרשימה לא נותן שורת Q, זמני תוקף או גבהים — הם נפתחים בלחיצה על
ה-`+`. הסקריפט הזה משחזר את הלחיצה ומדפיס מה חזר.

הניסיון הקודם נכשל כי הוא שלח את *כל* שדות הטופס, ובהם ששת כפתורי
ה-submit. דפדפן שולח כפתור אחד בלבד — זה שנלחץ — ו-ASP.NET בוחר את
המטפל לפי מה שהגיע. כאן נשלח רק `btnMoreInfo`.

הסקריפט לא כותב כלום. כלי חקירה בלבד.
"""

from __future__ import annotations

import http.cookiejar
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import iaa  # noqa: E402
import parse_qline  # noqa: E402

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# WebForms שומר את מצב הדף בסשן; בלי עוגייה ה-postback מגיע כסשן חדש.
_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_JAR))


def fetch(url: str, data: bytes | None = None, extra: dict | None = None):
    headers = {"User-Agent": BROWSER_UA, "Accept": "*/*", "Referer": iaa.NOTAM_URL}
    headers.update(extra or {})
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with _OPENER.open(request, timeout=45) as response:
            return iaa.decode(response.read()), response.status
    except urllib.error.HTTPError as exc:
        return iaa.decode(exc.read()), exc.code
    except Exception as exc:  # noqa: BLE001 — מדפיסים ומתקדמים
        return f"<{type(exc).__name__}: {exc}>", 0


def main() -> int:
    print("=" * 70)
    print("אבחון: כפתור ההרחבה")
    print("=" * 70)

    page, status = fetch(iaa.NOTAM_URL)
    rows = [r for r in iaa.parse_notam_page(page) if r.get("msg_num")]
    print(f"\nדף הרשימה: HTTP {status} · {len(page):,} bytes · {len(rows)} שורות")
    if not rows:
        print("אין שורות עם msg_num. עוצרים.")
        return 1

    payload = iaa.more_info_payload(page, rows[0]["msg_num"])
    buttons = [k for k in payload if k.startswith(("btn", "img"))]
    print(f"כפתורים במטען: {buttons}  (דפדפן שולח אחד בלבד)")

    for row in rows[:1]:
        msg_num = row["msg_num"]
        print(f"\n{'─' * 70}\n▶ {row['id']} · msg_num={msg_num}")
        body, status = fetch(
            iaa.NOTAM_URL,
            urllib.parse.urlencode(iaa.more_info_payload(page, msg_num)).encode(),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        detail = iaa.parse_more_info(body, msg_num)
        print(f"  HTTP {status} · {len(body):,} bytes "
              f"(הרשימה: {len(page):,}, הפרש {len(body) - len(page):+,}) · "
              f"שדות: {sorted(detail)}")
        if not detail:
            # התשובה גדלה, כלומר משהו נפתח — רק שהפרסר לא מזהה אותו.
            # מדפיסים את ה-HTML כמו שהוא במקום לנחש שמות מחלקות.
            import re as _re
            spot = body.find(f"divMoreInfo_{msg_num}")
            print(f"  לא נפתח לפי הפרסר. divMoreInfo_{msg_num} במיקום {spot}.")
            if spot != -1:
                print("  --- 3,000 תווים משם:")
                print("  " + _re.sub(r"\s+", " ", body[spot: spot + 3000]))
            classes = sorted(set(_re.findall(r'class="(more_[^"]+)"', body)))
            print(f"  מחלקות more_ בגוף: {classes}")
            continue
        for key in ("id", "airfield", "created", "valid_from", "valid_to"):
            if detail.get(key):
                print(f"    {key:11} {detail[key]}")
        raw = detail.get("raw", "")
        print(f"  --- הנוטאם הגולמי ({len(raw)} תווים):")
        print("      " + raw.replace("\n", "\n      "))
        parsed = parse_qline.parse_notam(raw)
        print(f"  --- אחרי הפרסר: q={bool(parsed.get('q'))} "
              f"תוקף={bool(parsed.get('valid_from'))} "
              f"גבהים={bool(parsed.get('altitude'))} "
              f"גיאומטריה={bool(parsed.get('geo'))}")
        if parsed.get("q"):
            q = parsed["q"]
            print(f"      {q.get('q_code')} · {q.get('subject')} · {q.get('condition')}")

        # לא מפציצים את השרת. שלוש בקשות באבחון, בהפרש שנייה.
        time.sleep(1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

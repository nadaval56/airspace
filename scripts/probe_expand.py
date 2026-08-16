#!/usr/bin/env python3
"""אבחון ממוקד: כפתור ההרחבה של רשות שדות התעופה.

דף הרשימה נותן מזהה, מיקום וטקסט — אבל **לא** שורת Q, לא זמני תוקף
ולא גבהים. כל אלה נפתחים בלחיצה על ה-`+`. `MoreInfo.js` מראה איך זה
היה עובד, אבל כל שורות הבקשה שם מסומנות כהערה:

    //  var requestURL = "AeroInfo.asmx?op=getMoreMsgInfo";

לעומת זאת `Locations.js` קורא ל-`AeroInfo.asmx` בפועל, עם SOAPAction
של tempuri.org. כלומר השירות חי — רק הקוד שקורא לו הוחלף. במקום לנחש
מקוד מבוטל, הסקריפט הזה מושך את ה-WSDL, קורא ממנו את שמות הפעולות
והפרמטרים, **ואז מפעיל בפועל** את הפעולה שנראית כמו ההרחבה.

הסקריפט לא כותב כלום. כלי חקירה בלבד.
"""

from __future__ import annotations

import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import iaa  # noqa: E402

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
ASMX = f"{iaa.BASE}/AeroInfo.asmx"


def fetch(url: str, data: bytes | None = None, extra: dict | None = None):
    """מחזיר (גוף, סטטוס). לא זורק — כישלון הוא תוצאה לגיטימית באבחון."""
    headers = {"User-Agent": BROWSER_UA, "Accept": "*/*", "Referer": iaa.NOTAM_URL}
    headers.update(extra or {})
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return iaa.decode(response.read()), response.status
    except urllib.error.HTTPError as exc:
        return iaa.decode(exc.read()), exc.code
    except Exception as exc:  # noqa: BLE001 — מדפיסים ומתקדמים
        return f"<{type(exc).__name__}: {exc}>", 0


def head(title: str) -> None:
    print(f"\n{'─' * 70}\n▶ {title}")


# ---------------------------------------------------------------------------
# קריאת החוזה
# ---------------------------------------------------------------------------

_OP_RE = re.compile(r'<(?:wsdl:)?operation\s+name="([^"]+)"', re.I)
_NS_RE = re.compile(r'targetNamespace="([^"]+)"')
# הגדרת פרמטרים של פעולה בסכימה:
#   <s:element name="OP"><s:complexType><s:sequence>
#     <s:element minOccurs="0" maxOccurs="1" name="msgNum" type="s:string" />
_ELEMENT_RE = re.compile(
    r'<s:element[^>]*\sname="(\w+)"[^>]*>(.*?)</s:element>', re.S | re.I
)
_PARAM_RE = re.compile(r'<s:element[^>]*\sname="(\w+)"[^>]*type="([^"]+)"', re.I)


def read_contract(wsdl: str) -> tuple[str, dict[str, list[tuple[str, str]]]]:
    """מחזיר (מרחב שמות, {שם פעולה: [(פרמטר, טיפוס)]})."""
    namespace = (_NS_RE.search(wsdl) or [None, "http://tempuri.org/"])[1]
    params: dict[str, list[tuple[str, str]]] = {}
    for name, body in _ELEMENT_RE.findall(wsdl):
        if "<s:sequence" in body or "<s:complexType" in body:
            params[name] = _PARAM_RE.findall(body)
    return namespace, params


def soap_call(namespace: str, operation: str, values: dict[str, str]):
    """SOAP 1.1 — הדפוס המדויק ש-Locations.js משתמש בו."""
    fields = "".join(f"<{k}>{v}</{k}>" for k, v in values.items())
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xmlns:xsd="http://www.w3.org/2001/XMLSchema"'
        ' xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
        f'<{operation} xmlns="{namespace}">{fields}</{operation}>'
        "</soap:Body></soap:Envelope>"
    )
    return fetch(
        ASMX,
        envelope.encode("utf-8"),
        {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f"{namespace.rstrip('/')}/{operation}",
        },
    )


def show_result(label: str, body: str, status: int) -> bool:
    """מדפיס תוצאה מקוצרת. מחזיר True אם חזר תוכן אמיתי ולא Fault."""
    fault = re.search(r"<(?:soap:)?Fault>.*?<faultstring>(.*?)</faultstring>", body, re.S)
    if fault:
        print(f"    {label}: HTTP {status} · Fault · {fault.group(1).strip()[:150]}")
        return False
    inner = re.search(r"<\w*Result[^>]*>(.*?)</\w*Result>", body, re.S)
    payload = inner.group(1) if inner else body
    payload = re.sub(r"\s+", " ", payload).strip()
    print(f"    {label}: HTTP {status} · {len(body):,} bytes · תוכן: {payload[:600]!r}")
    return bool(payload) and status == 200


def main() -> int:
    print("=" * 70)
    print("אבחון: כפתור ההרחבה — AeroInfo.asmx")
    print("=" * 70)

    # (1) מזהה אמיתי לניסוי, מהדף החי.
    head("מספר הודעה לניסוי")
    page, status = fetch(iaa.NOTAM_URL)
    rows = [r for r in iaa.parse_notam_page(page) if r.get("msg_num")]
    print(f"  דף הרשימה: HTTP {status} · {len(page):,} bytes · {len(rows)} שורות עם msg_num")
    if not rows:
        print("  אין msg_num בדף — כפתור ההרחבה לא נבנה כך. עוצרים.")
        return 1
    sample = rows[0]
    msg_num = sample["msg_num"]
    print(f"  לדוגמה: {sample['id']} · msg_num={msg_num}")
    print(f"  הטקסט מהרשימה: {(sample.get('text') or '')[:200]!r}")

    # (2) החוזה עצמו.
    head("WSDL")
    wsdl, status = fetch(f"{ASMX}?WSDL")
    print(f"  HTTP {status} · {len(wsdl):,} bytes")
    if status != 200:
        print("  " + wsdl[:400].replace("\n", "\n  "))
        return 1
    namespace, params = read_contract(wsdl)
    operations = sorted(set(_OP_RE.findall(wsdl)))
    print(f"  מרחב שמות: {namespace}")
    print(f"  {len(operations)} פעולות: {operations}")
    for operation in operations:
        signature = params.get(operation, [])
        rendered = ", ".join(f"{n}: {t.split(':')[-1]}" for n, t in signature)
        print(f"    {operation}({rendered})")

    # (3) הפעלה בפועל של כל פעולה שנראית כמו ההרחבה.
    head("הפעלה")
    candidates = [o for o in operations if re.search(r"more|msg|notam|info|text", o, re.I)]
    print(f"  מועמדים: {candidates or 'אין — מנסים הכול'}")
    guesses = {
        "msgnum": msg_num, "messagenum": msg_num, "num": msg_num, "id": msg_num,
        "msgid": msg_num, "messageid": msg_num,
        "mode": "0", "currorhist": "C", "lang": "1", "language": "1",
        "msgtype": "Notam", "type": "Notam",
    }
    for operation in candidates or operations:
        signature = params.get(operation)
        if signature is None:
            print(f"    {operation}: אין הגדרת פרמטרים בסכימה — מדלגים")
            continue
        values = {name: guesses.get(name.lower(), "") for name, _ in signature}
        print(f"  {operation}({values})")
        body, status = soap_call(namespace, operation, values)
        if show_result("SOAP", body, status):
            continue
        # ה-WebForms הישן חושף את אותן פעולות גם ב-GET/POST פשוט.
        query = "&".join(f"{k}={v}" for k, v in values.items())
        body, status = fetch(f"{ASMX}/{operation}?{query}")
        show_result("GET ", body, status)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

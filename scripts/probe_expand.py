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

import http.cookiejar
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

# WebForms שומר את מצב הדף בסשן. בלי עוגייה, ה-postback מגיע כסשן חדש
# והשרת פשוט מחזיר את הדף ההתחלתי — בדיוק מה שקרה בניסיון הראשון.
_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_JAR))


def fetch(url: str, data: bytes | None = None, extra: dict | None = None):
    """מחזיר (גוף, סטטוס). לא זורק — כישלון הוא תוצאה לגיטימית באבחון."""
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

    # `MoreImg_0` הוא **אינדקס שורה**, לא מזהה הודעה. מה שמעניין הוא מה
    # הכפתור עושה בפועל: onclick עם שם פונקציה, או __doPostBack של
    # WebForms — ואלה שני עולמות שונים לגמרי.
    head("סימון הכפתור בדף")
    ids = list(dict.fromkeys(re.findall(r'id="([^"]*[Mm]ore[^"]*)"', page)))
    print(f"  {len(ids)} מזהי 'More' ייחודיים, ראשונים: {ids[:8]}")
    # ה-JS לוקח את המזהה של האב החמישי וחותך ממנו 12 תווים:
    #   f_getMoreInfo(this.parentNode(x5).id.substr(12), 'more')
    # כלומר msgNum הוא **הזנב של מזהה השורה**, לא האינדקס של התמונה.
    hit = re.search(r"MoreImg_\d+", page)
    if hit:
        start = max(0, hit.start() - 2500)
        chunk = re.sub(r"\s+", " ", page[start: hit.start() + 300])
        print(f"  --- 2,500 תווים לפני MoreImg_0 (מזהי האבות):\n  {chunk}")

    # (2) ההרחבה היא postback של WebForms, לא שירות. `f_getMoreInfo`
    # ממלאת ארבעה שדות מוסתרים ולוחצת על כפתור:
    #
    #   hidMsgNum = msgNum;  hidMode = mode;  hidCurOrHist = 'Current';
    #   hidTblClientId = "";  btnMoreInfo.click();
    #
    # אז משחזרים בדיוק את זה. ה-.asmx נזנח — כל הקוד שקורא לו מסומן
    # כהערה, ו-`?WSDL` חסום על ידי Radware. לא נוגעים בו.
    head("postback של ההרחבה")
    import urllib.parse

    base = iaa.more_info_payload(page, msg_num)
    print(f"  עוגיות: {[c.name for c in _JAR]}")
    print(f"  btnMoreInfo בטופס: {'btnMoreInfo' in base}")

    # הדף עטוף ב-UpdatePanel-ים. אם `btnMoreInfo` רשום כטריגר אסינכרוני,
    # postback מלא לא יפעיל את הקוד שממלא את הטבלה — צריך את הדפוס של
    # ASP.NET AJAX. שם ה-ScriptManager מופיע בהפעלה שלו בדף.
    manager = re.search(r"PageRequestManager\._initialize\(\s*'([^']+)'", page)
    panels = list(dict.fromkeys(re.findall(r'id="(UpdatePanel\d*)"', page)))
    print(f"  ScriptManager: {manager.group(1) if manager else 'לא נמצא'} · פאנלים: {panels}")

    def block(html: str) -> str:
        """הבלוק שאמור להתמלא — כולל טבלת הפרטים שבתוכו."""
        spot = html.find(f"tblMoreInfo1_{msg_num}")
        return re.sub(r"\s+", " ", html[spot: spot + 5000]) if spot != -1 else ""

    attempts = [("postback מלא", base, {})]
    if manager:
        # `<שם הפאנל>|<שם הכפתור>` הוא הפורמט שהדפדפן שולח.
        async_fields = dict(base)
        async_fields[manager.group(1)] = f"{panels[0] if panels else 'UpdatePanel3'}|btnMoreInfo"
        async_fields["__ASYNCPOST"] = "true"
        attempts.append(("postback אסינכרוני", async_fields, {"X-MicrosoftAjax": "Delta=true"}))

    baseline = block(page)
    print(f"  הבלוק לפני: {len(baseline)} תווים")
    for label, payload, extra in attempts:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        headers.update(extra)
        body, status = fetch(iaa.NOTAM_URL, urllib.parse.urlencode(payload).encode(), headers)
        after = block(body)
        print(f"\n  ▸ {label}: HTTP {status} · {len(body):,} bytes · הבלוק {len(after)} תווים")
        print(f"    השתנה: {after != baseline}")
        print(f"    parse_more_info: {iaa.parse_more_info(body)}")
        print(f"    'Valid To' בגוף: {body.count('Valid To')} · 'trMore': {body.count('trMore')}")
        if after and after != baseline:
            print(f"    --- הבלוק:\n    {after[:2200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

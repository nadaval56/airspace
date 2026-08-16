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
    hit = re.search(r"MoreImg_\d+", page)
    if hit:
        start = page.rfind("<td", 0, hit.start())
        print("  " + page[max(0, start): hit.start() + 700].replace("\n", "\n  ")[:1600])

    # `f_getMoreInfo` קיימת וחיה, אבל אין בקובץ שום שורת `.open(` שאינה
    # הערה. כלומר הבקשה נבנית במקום אחר — צריך לקרוא את הגוף המלא.
    # אין בכל MoreInfo.js אף שורת `.open(` שאינה הערה — כל בניית הבקשה
    # מסומנת כהערה. השערה: אין בקשה. הדף שוקל 1.4MB ל-127 נוטאמים, הרבה
    # מעבר לטקסט הנראה, ולכן ייתכן שתוכן ההרחבה כבר מוטמע בו ו-JS רק
    # מחליף display. אם זה נכון — זמני התוקף כבר אצלנו.
    head("האם ההרחבה כבר בדף?")
    for needle in ("divMoreInfo_", "tblMoreInfo1_", "Valid From", "FromDate", "ToDate", "getMoreMsgInfo"):
        print(f"  {needle!r}: {page.count(needle)} מופעים")
    spot = page.find("divMoreInfo_0")
    if spot != -1:
        print("  --- HTML סביב divMoreInfo_0:")
        print("  " + page[spot - 200: spot + 1400].replace("\n", "\n  "))

    js, status = fetch(f"{iaa.BASE}/JS/MoreInfo.js")
    print(f"\n  --- MoreInfo.js ({status}, {len(js):,} bytes)")
    # החצי השני של הקובץ — `f_buildMoreMsgInfo(xml)` — כבר נקרא, והוא
    # מראה בדיוק מה חוזר: XML עם NotamID, Location, Airfield, CreateDate,
    # FromDate ו-ToDate, ואחריו רשימת MsgText. חסר רק החצי הראשון:
    # איך הבקשה נשלחת. חותכים משם ועד תחילת הבנייה.
    start = js.find("function f_getMoreInfo")
    end = js.find("function f_buildMoreMsgInfo")
    if start == -1:
        print("      אין f_getMoreInfo בקובץ.")
    else:
        section = js[start: end if end > start else start + 4000]
        live = [ln for ln in section.splitlines() if ln.strip() and not ln.strip().startswith("//")]
        print(f"      --- f_getMoreInfo: {len(section):,} תווים, {len(live)} שורות שאינן הערה:")
        for line in live:
            print(f"      {line.strip()[:170]}")

    # (2) ההרחבה היא postback של WebForms, לא שירות. `f_getMoreInfo`
    # ממלאת ארבעה שדות מוסתרים ולוחצת על כפתור:
    #
    #   hidMsgNum = msgNum;  hidMode = mode;  hidCurOrHist = 'Current';
    #   hidTblClientId = "";  btnMoreInfo.click();
    #
    # אז משחזרים בדיוק את זה. ה-.asmx נזנח — כל הקוד שקורא לו מסומן
    # כהערה, ו-`?WSDL` חסום על ידי Radware. לא נוגעים בו.
    head("postback של ההרחבה")
    fields = iaa.more_info_payload(page, msg_num)
    print(f"  עוגיות: {[c.name for c in _JAR]}")
    print(f"  {len(fields)} שדות: {sorted(fields)}")
    print(f"  btnMoreInfo בטופס: {'btnMoreInfo' in fields}")
    import urllib.parse
    body, status = fetch(
        iaa.NOTAM_URL,
        urllib.parse.urlencode(fields).encode(),
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    print(f"  HTTP {status} · {len(body):,} bytes (הרשימה: {len(page):,})")
    print(f"  parse_more_info: {iaa.parse_more_info(body)}")

    # ההשוואה היא הבדיקה האמיתית: מה השתנה בתוך divMoreInfo_<n> בין
    # הדף המקורי לתשובת ה-postback. אם כלום לא השתנה — לא נפתח כלום.
    def block(html: str) -> str:
        spot = html.find(f'id="divMoreInfo_{msg_num}"')
        return re.sub(r"\s+", " ", html[spot: spot + 1800]) if spot != -1 else ""

    before, after = block(page), block(body)
    print(f"  divMoreInfo_{msg_num}: לפני {len(before)} תווים, אחרי {len(after)}")
    print(f"  זהה: {before == after}")
    print(f"  --- אחרי:\n  {after[:1600]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

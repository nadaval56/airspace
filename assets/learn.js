/* ---------------------------------------------------------------------------
   איך קוראים נוטאם — חלק ב'
   ---------------------------------------------------------------------------
   העמוד הראשי עונה על "איפה אפשר לטוס". העמוד הזה עונה על השאלה
   שמגיעה מיד אחריה: **מה כתוב שם בכלל.**

   נוטאם אינו טקסט חופשי אלא טופס בעל שדות ממוספרים, וזו הבשורה הטובה
   היחידה בסיפור: אי אפשר ללמוד את כל הניסוחים, אבל אפשר ללמוד את
   הטופס — ואז כל הודעה נקראת באותו מסלול.

   העמוד עצמאי לגמרי מ-app.js. הוא לא טוען את Leaflet, לא מצייר מפה,
   ולא נוגע בשום דבר שהמסך הראשי עושה. מה שהוא כן עושה: קורא את
   `data/notams.json` כדי ללמד על **הודעות אמיתיות מהיום** ולא על
   דוגמאות מומצאות. אם הקריאה נכשלת — הדף ממשיך לעבוד על הדוגמאות
   המוטבעות בקוד, כי שיעור שלא נטען הוא שיעור שלא נלמד.

   הפרסור כאן הוא נמל (port) של scripts/parse_qline.py, בכוונה בלי
   שינויים בלוגיקה. שם הוא רץ בפייתון ומייצר את data/notams.json; כאן
   הוא רץ בדפדפן על טקסט שהמשתמש מדביק, וחייב להגיע לאותה תוצאה.
--------------------------------------------------------------------------- */

'use strict';

const TZ = 'Asia/Jerusalem';
const FEED_URL = 'data/notams.json';
const FIELDS_URL = 'data/aip-aerodromes.geojson';

/* --- טבלאות פענוח ------------------------------------------------------ */

/*
  שתי הערות חשובות לפני הטבלאות.

  **1. הטבלה חלקית, ובכוונה.** היא זהה לזו שב-scripts/parse_qline.py —
  כלומר מכסה את מה שאומת מול נוסחי ההודעות שנשאו את הקוד בפועל,
  ולא את מה שהזיכרון מציע. אותו כלל שתקף למפה תקף כאן כפליים: מי
  שבא ללמוד סומך על התווית יותר מכל אחד אחר, ותווית מומצאת תלמד
  אותו דבר שגוי. קוד שאינו בטבלה מוצג גולמי, והדף אומר זאת במפורש
  במקום לנחש. מה שכן נלמד במקומו הוא **המבנה** — משפחת האות
  הראשונה וקבוצת המצב — שממנה אפשר להסיק את הכיוון גם בלי הערך.

  התוספת היחידה על הטבלה של הפרסור היא הקוד LW, ומאותו טעם בדיוק:
  27 הודעות בפיד נושאות אותו, וכולן פותחות ב-"WILL TAKE PLACE".

  **2. תווית אינה תחליף לנוסח.** קוד Q מספר על מה ההודעה ומה מצבו,
  אבל הפרטים — איפה בדיוק, מאיזה גובה, למי — נמצאים רק בפריט E).
  לכן כל מסך בעמוד הזה שמראה פענוח מראה לצדו גם את הטקסט המקורי.
*/

const Q_FAMILY = {
  A: 'מרחב אווירי — מבנה, גבולות ונתיבים',
  C: 'תקשורת ומעקב',
  F: 'מתקנים ושירותי שדה',
  I: 'עזרי גישת מכשירים',
  L: 'תאורה',
  M: 'משטחי תנועה — מסלולים והסעה',
  N: 'עזרי ניווט',
  O: 'מידע תפעולי אחר',
  P: 'נהלי טיסה',
  R: 'מגבלות מרחב אווירי',
  S: 'שירותי תעבורה אווירית',
  W: 'אזהרות ניווט — פעילות בשטח',
};

const Q_SUBJECT = {
  // A — מרחב אווירי ומבנהו
  AA: 'גובה מינימלי',
  AC: 'אזור בקרת שדה (CTR)',
  AD: 'אזור זיהוי הגנה אווירית (ADIZ)',
  AE: 'אזור בקרה (CTA)',
  AF: 'אזור מידע טיסה (FIR)',
  AN: 'נתיב ניווט שטח (RNAV)',
  AR: 'נתיב ATS',
  AT: 'אזור בקרה מסוף (TMA)',
  // C — תקשורת
  CA: 'מתקן קשר אוויר-קרקע',
  // F — שדה ושירותיו
  FA: 'שדה תעופה',
  FU: 'דלק',
  // I — גישת מכשירים
  IS: 'מערכת ILS',
  // L — תאורה
  LP: 'מחוון זווית גישה (PAPI)',
  // M — משטחי תנועה
  MP: 'עמדת חניה למטוס',
  MR: 'מסלול',
  MT: 'מנחת',
  MX: 'מסלול הסעה',
  // N — עזרי ניווט
  NA: 'עזרי ניווט',
  NB: 'משואת NDB',
  ND: 'משואת DME',
  NI: 'מערכת ILS',
  NM: 'משואת VOR/DME',
  NV: 'משואת VOR',
  // O — מידע תפעולי אחר
  OA: 'שירות מידע תעופתי (AIS)',
  OB: 'מכשול',
  OL: 'תאורת מכשול',
  // P — נהלי טיסה
  PD: 'נוהל המראת מכשירים (SID)',
  PO: 'גובה עקיפת מכשולים (OCA/H)',
  // R — מגבלות מרחב אווירי
  RA: 'אזור שמור לפעילות',
  RD: 'אזור מסוכן',
  RM: 'אזור צבאי',
  RO: 'אזור מבצעי',
  RP: 'אזור אסור לטיסה',
  RR: 'אזור מוגבל',
  RT: 'אזור מוגבל זמנית',
  // W — אזהרות ניווט
  WA: 'פעילות אווירית',
  WB: 'אווירובטיקה',
  WC: 'כדור פורח קשור / עפיפון',
  WD: 'תרגיל צניחה',
  WE: 'תרגיל / אימון',
  WF: 'ירי תותחים',
  WG: 'ירי קרקע-אוויר',
  WH: 'ירי / חומרי נפץ',
  WJ: 'ירי טילים',
  WL: 'שיגור רקטות',
  WM: 'ירי טילים / רקטות',
  WP: 'צניחה חופשית',
  WR: 'פעילות רדיואקטיבית',
  WS: 'פעילות בליסטית',
  WT: 'פעילות דאונים / רחיפה',
  WU: 'כלי טיס בלתי מאויש (כטב"ם)',
  WV: 'תעופת ראווה',
  WW: 'פעילות בגובה רב',
  WZ: 'מרחב שמור זמנית',
  // מיוחדים
  GW: 'שירותי GNSS — כלל אזוריים',
  KK: 'רשימת בדיקה (CHECKLIST)',
};

/*
  הסבר בשפה רגילה למונחים שהתווית שלהם היא ראשי תיבות או מונח מקצועי.
  התווית לבדה אומרת מה זה למי שכבר יודע; השורה הזאת אומרת את זה למי
  שלא — וזה כל הרעיון של העמוד הזה.
*/
const Q_SUBJECT_NOTE = {
  AA: 'הגובה הנמוך ביותר שמותר לטוס בו באזור.',
  AC: 'מרחב מבוקר סביב שדה תעופה, מהקרקע ומעלה.',
  AD: 'אזור שבו נדרש זיהוי כלי הטיס מטעמי ביטחון.',
  AE: 'מרחב מבוקר שמתחיל בגובה מוגדר ומעלה, לא מהקרקע.',
  AF: 'האזור שבו ניתן שירות מידע טיסה. מרחב תל אביב כולו הוא LLLL.',
  AN: 'נתיב המוגדר בנקודות ציון ולא במשואות קרקע.',
  AR: 'נתיב תעופה מפורסם שבו זורמת תעבורה מבוקרת.',
  AT: 'מרחב מבוקר מעל צומת שדות עמוס, שבו מתנקזות המראות ונחיתות.',
  CA: 'תדרי הרדיו שבהם מדברים עם הבקרה.',
  GW: 'שיבוש או תקלה בקליטת לוויין (GPS) בכל האזור, לא בנקודה אחת.',
  IS: 'מערכת נחיתה בהנחיית מכשירים — אלומות רדיו שמובילות למסלול.',
  KK: 'הודעה תקופתית שמונה את כל הנוטאמים בתוקף. אינה מגבלה בפני עצמה.',
  LP: 'פנסים ליד המסלול שמראים לטייס אם הגישה גבוהה או נמוכה מדי.',
  MP: 'עמדת החניה של המטוס במנחת, לא המסלול עצמו.',
  MX: 'הדרך שבה המטוס נוסע על הקרקע בין המסלול לחניה.',
  NB: 'משואת ניווט המשדרת בגלים בינוניים; כיוון בלבד.',
  ND: 'משואה המוסרת מרחק בלבד.',
  NM: 'משואת ניווט שמוסרת גם כיוון וגם מרחק.',
  NV: 'משואת ניווט המוסרת כיוון ביחס לצפון.',
  OA: 'הודעה על שינוי בפמ"ת עצמו. אינה מגבלה בשטח.',
  OB: 'עצם פיזי שמתנשא לגובה — עגורן, אנטנה, טורבינה.',
  PD: 'מסלול ההמראה המפורסם של השדה.',
  PO: 'הגובה הנמוך ביותר שממנו מותר להמשיך בגישה בלי לראות את המסלול.',
  RR: 'אזור שהטיסה בו מותנית באישור מראש.',
  RT: 'אזור שנסגר לזמן קצוב ואינו מופיע במפות הקבועות.',
  WC: 'בלון הקשור לקרקע בכבל. הכבל — לא הבלון — הוא המכשול.',
  WP: 'אזור שבו מתבצעות קפיצות צניחה.',
  WT: 'דאונים ורחפנים אינם נושאים מנוע, ואינם יכולים לפנות מהר.',
  WU: 'פעילות כלי טיס בלתי מאויש — רחפן או מזל"ט.',
  WZ: 'מרחב שהופרש זמנית לפעילות מסוימת וסגור לשאר.',
};

const Q_CONDITION = {
  AC: 'הופסק',
  AD: 'זמין לשימוש יומי',
  AH: 'פעיל בשעות שפורסמו',
  AK: 'חזר לפעילות רגילה',
  AL: 'פעיל בכפוף למגבלות',
  AM: 'פעיל בשעות צבאיות',
  AN: 'זמין לתעבורה לילית',
  AO: 'מבצעי',
  AP: 'פעיל — נדרשת בקשה מראש',
  AR: 'פעיל בשעות שפורסמו',
  AS: 'מושבת',
  AU: 'לא זמין',
  AW: 'הוסר לחלוטין',
  AX: 'פתוח מחדש',
  CA: 'מופעל',
  CC: 'הושלם',
  CD: 'מבוטל / מושבת',
  CE: 'הוקם',
  CF: 'פועל בתדר שונה',
  CG: 'פורק',
  CH: 'שונה',
  CI: 'מזוהה כעת כ-',
  CL: 'בוטל / חוסל',
  CM: 'הועבר למקום אחר',
  CN: 'מבוטל',
  CO: 'פועל',
  CP: 'פועל בהספק מופחת',
  CR: 'מוחלף ב-',
  CS: 'מותקן',
  CT: 'בבדיקה',
  HV: 'עבודות בעיצומן',
  LC: 'סגור',
  LN: 'סגור בשעות לילה',
  LP: 'אסור',
  LR: 'מוגבל',
  LS: 'לא בטוח לשימוש',
  LT: 'מוגבל ל-',
  LV: 'פעולה נורמלית חודשה',
  LW: 'יתקיים',
  LX: 'פעיל',
  TT: 'שינוי זמני',
  XX: 'טקסט חופשי',
};

const Q_SCOPE = {
  A: 'שדה תעופה',
  E: 'נתיב טיסה',
  W: 'אזהרה למרחב',
  K: 'רשימת בדיקה',
  AE: 'שדה תעופה ונתיב',
};

/*
  שדה 3 בשורת Q — למי ההודעה נוגעת. הוא **לא** אומר מי מותר לו לטוס
  שם, אלא לתדריך של מי ההודעה נכנסת. IV הוא רוב הפיד: גם למכשירים
  וגם לראייה.
*/
const Q_TRAFFIC = {
  I: 'טיסות מכשירים (IFR)',
  V: 'טיסות ראייה (VFR)',
  IV: 'מכשירים וראייה — כולם',
  K: 'רשימת בדיקה',
};

/*
  שדה 4 — למה ההודעה מיועדת. אותיות מצטרפות: NBO הוא הצירוף הנפוץ
  ביותר, ופירושו הודעה שראויה לתשומת לב מיידית, נכנסת לתדריך הטרום־
  טיסתי, ונוגעת לביצוע הטיסה.
*/
const Q_PURPOSE = {
  N: 'ראויה לתשומת לב מיידית',
  B: 'נכנסת לתדריך הטרום־טיסתי (PIB)',
  O: 'נוגעת לביצוע הטיסה',
  M: 'שונות — אינה נכנסת לתדריך אוטומטית',
  K: 'רשימת בדיקה',
};

const NOTAM_TYPE = {
  NOTAMN: {
    label: 'הודעה חדשה',
    note: 'N מלשון New. מידע שלא היה קודם, ואינו מחליף דבר.',
  },
  NOTAMR: {
    label: 'הודעה מחליפה',
    note: 'R מלשון Replace. מבטלת הודעה קודמת ובאה במקומה — המזהה של המוחלפת מופיע מיד אחריה.',
  },
  NOTAMC: {
    label: 'הודעת ביטול',
    note: 'C מלשון Cancel. מבטלת הודעה קודמת בלי להחליפה. אחריה אין עוד מגבלה.',
  },
};

const ITEM_INFO = {
  /*
    הכותרת אינה פריט ממוספר, ובכל זאת היא חלק מההודעה — ומי שלוחץ
    על כל השאר מנסה ללחוץ גם עליה. השורה הראשונה נושאת שני דברים
    שקובעים איך לקרוא את כל מה שאחריה: מי ההודעה, ואם היא מחליפה
    או מבטלת קודמת.
  */
  HEAD: {
    name: 'הכותרת',
    short: 'מי ההודעה, ומה סוגה',
    text: 'מזהה ההודעה — אות הסדרה, מספר רץ ושנה — ואחריו סוגה. בפיד הישראלי סדרה A נושאת בעיקר את הודעות שדות התעופה, וסדרה C את ההודעות המקומיות: בועות אולטרלייט, כדורים פורחים, רחפנים וצניחה.',
  },
  Q: {
    name: 'שורת Q',
    short: 'התקציר הממוכן',
    text: 'שמונה שדות מופרדים בלוכסן, שנועדו למחשב ולא לאדם: אזור המידע, קוד הנושא, למי זה נוגע, למה, היכן, מאיזה גובה עד איזה, ובאיזה מעגל. זו השורה שמאפשרת לסנן אלפי הודעות בלי לקרוא אף אחת מהן.',
  },
  A: { name: 'פריט A', short: 'איפה — מזהה המקום', text: 'קוד ICAO של השדה או של אזור המידע. LLLL הוא כל מרחב תל אביב; LLBG הוא נתב"ג בלבד.' },
  B: { name: 'פריט B', short: 'ממתי', text: 'תחילת התוקף, בפורמט YYMMDDHHMM ובשעון UTC. אפשר גם WIE — מיידי.' },
  C: { name: 'פריט C', short: 'עד מתי', text: 'סוף התוקף, באותו פורמט. PERM = קבוע. EST = מוערך, כלומר עשוי להשתנות בלי הודעה נוספת.' },
  D: { name: 'פריט D', short: 'לוח זמנים בתוך החלון', text: 'ההודעה פעילה רק בשעות האלה, בתוך הטווח של B ו-C. שדה שקל לפספס — ובלעדיו קוראים סגירה רצופה במקום שעתיים ביום.' },
  E: { name: 'פריט E', short: 'מה בעצם קורה', text: 'הנוסח החופשי. כאן נמצאים כל הפרטים שהקודים לא נושאים — הגבול המדויק, הסיבה, האזהרה, ומי מתאם.' },
  F: { name: 'פריט F', short: 'גבול תחתון', text: 'רצפת המגבלה בניסוח מפורש. מדויק יותר משורת Q, ולכן הוא גובר עליה.' },
  G: { name: 'פריט G', short: 'גבול עליון', text: 'תקרת המגבלה. שימו לב אם היא AMSL (מעל פני הים) או AGL (מעל הקרקע) — ההבדל בהרים הוא מאות רגל.' },
};

/* --- מילון הקיצורים ---------------------------------------------------- */

/*
  הרשימה נבנתה מהפיד עצמו ולא מתוך ספר: הוצאו כל צירופי האותיות
  הגדולות מ-129 ההודעות הפעילות, מוינו לפי תדירות, וכל ערך שנכנס
  לכאן נבדק מול המשפט שבו הוא מופיע. לכן אין כאן ערכים שנכונים
  בתאוריה ואינם מופיעים אף פעם בישראל, ויש כאן ערכים שאינם בשום
  רשימה רשמית — BUBBLE, למשל, הוא מונח מקומי לחלוטין.

  `he` הוא התרגום, `note` הוא מה שהתרגום לבדו לא מספר. השדה `hot`
  מסמן קיצור שמופיע עשרות פעמים בפיד — אלה שכדאי לדעת בעל פה.
*/
const ABBR_GROUPS = {
  time: 'זמן ולוח זמנים',
  space: 'מרחב, מיקום וגובה',
  act: 'פעילות ומצב',
  field: 'שדה, מסלול ומכשולים',
  nav: 'ניווט, קשר ומכשירים',
  who: 'מי טס שם',
  admin: 'מנהלה ופרסומים',
  glue: 'מילות קישור',
};

const ABBR = {
  // --- זמן ---
  UTC:   { g: 'time', he: 'זמן עולמי מתואם', note: 'כל הזמנים בנוטאם הם UTC. בישראל מוסיפים שלוש שעות בקיץ ושעתיים בחורף.' },
  PERM:  { g: 'time', he: 'קבוע', note: 'ההודעה אינה פגה. בדרך כלל סימן שהשינוי ייכנס לפמ"ת עצמו.' },
  EST:   { g: 'time', he: 'מוערך', note: 'זמן הסיום הוא הערכה. ההודעה עשויה להימשך או להסתיים מוקדם, בלי הודעה נוספת.' },
  WIE:   { g: 'time', he: 'בתוקף מיידית', note: 'With Immediate Effect. מופיע במקום תאריך בפריט B.' },
  WEF:   { g: 'time', he: 'בתוקף מ־', note: 'With Effect From. מופיע בגוף ההודעה, בדרך כלל בהודעות עדכון פמ"ת.' },
  TIL:   { g: 'time', he: 'עד' },
  UFN:   { g: 'time', he: 'עד להודעה חדשה', note: 'Until Further Notice.' },
  DAILY: { g: 'time', he: 'מדי יום', note: 'בפריט D — השעות שאחריו חוזרות בכל יום שבתוך חלון B–C.' },
  H24:   { g: 'time', he: 'מסביב לשעון' },
  HJ:    { g: 'time', he: 'בשעות אור' },
  HN:    { g: 'time', he: 'בשעות חושך' },
  SR:    { g: 'time', he: 'זריחה' },
  SS:    { g: 'time', he: 'שקיעה' },
  HR:    { g: 'time', he: 'שעות' },
  MIN:   { g: 'time', he: 'דקות', note: 'בהקשר של זמן. כשמדובר בגובה — ראו MNM.' },
  AUG:   { g: 'time', he: 'אוגוסט', note: 'שמות החודשים מופיעים בקיצור בן שלוש אותיות.' },

  // --- מרחב וגובה ---
  AMSL:  { g: 'space', hot: true, he: 'מעל פני הים', note: 'הגובה שהאלטימטר מראה. זה הגובה שמשווים אליו כמעט תמיד.' },
  AGL:   { g: 'space', hot: true, he: 'מעל פני הקרקע', note: 'גובה יחסי לשטח שמתחת. בהר, 500 רגל AGL הם הרבה יותר מ-500 רגל AMSL.' },
  MSL:   { g: 'space', he: 'פני הים' },
  GND:   { g: 'space', hot: true, he: 'קרקע', note: 'רצפת המגבלה נוגעת בקרקע — אין מתחתיה מרווח מעבר.' },
  SFC:   { g: 'space', he: 'פני השטח', note: 'שם נרדף ל-GND בפריטי F.' },
  UNL:   { g: 'space', he: 'ללא הגבלת גובה', note: 'אין תקרה. אי אפשר לעבור מעל האזור הזה.' },
  FL:    { g: 'space', he: 'רמת טיסה', note: 'מאות רגל בלחץ תקני: FL080 הם 8,000 רגל.' },
  FT:    { g: 'space', hot: true, he: 'רגל', note: 'רגל אחת ≈ 30.5 ס"מ. 1,000 רגל ≈ 305 מטר.' },
  M:     { g: 'space', he: 'מטר', note: 'הודעות ישראליות נוקבות לעתים בשני האופנים: 600M AGL, ולצדו 3,700FT AMSL.' },
  KM:    { g: 'space', he: 'קילומטר' },
  NM:    { g: 'space', hot: true, he: 'מייל ימי', note: 'מייל ימי אחד = 1,852 מטר. רדיוסים בשורת Q נמדדים ביחידה הזאת.' },
  ELEV:  { g: 'space', he: 'גובה המקום', note: 'גובה הקרקע עצמה מעל פני הים, לא גובה הטיסה.' },
  MNM:   { g: 'space', he: 'מינימלי' },
  MAX:   { g: 'space', he: 'מקסימלי' },
  RADIUS:{ g: 'space', he: 'רדיוס' },
  PSN:   { g: 'space', hot: true, he: 'מיקום', note: 'Position. אחריו באות קואורדינטות בפורמט DDMMSSN DDDMMSSE.' },
  CENTERED: { g: 'space', he: 'שמרכזו', note: 'מגדיר מעגל: רדיוס + נקודת מרכז.' },
  AREA:  { g: 'space', he: 'אזור' },
  BDRY:  { g: 'space', he: 'גבול' },
  BOUNDRAY: { g: 'space', he: 'גבול', note: 'שגיאת כתיב שחוזרת בהודעות המקומיות. הכוונה BOUNDARY.' },
  CTR:   { g: 'space', he: 'אזור בקרת שדה', note: 'מרחב מבוקר סביב שדה, מהקרקע ומעלה. כניסה מחייבת אישור.' },
  CTA:   { g: 'space', he: 'אזור בקרה', note: 'מרחב מבוקר שמתחיל בגובה מסוים ומעלה.' },
  TMA:   { g: 'space', he: 'אזור בקרה מסוף', note: 'המרחב שמעל צומת שדות עמוס.' },
  FIR:   { g: 'space', he: 'אזור מידע טיסה', note: 'מרחב תל אביב כולו הוא LLLL.' },
  ADIZ:  { g: 'space', he: 'אזור זיהוי הגנה אווירית' },
  AIRSPACE: { g: 'space', he: 'מרחב אווירי' },

  // --- פעילות ומצב ---
  ACT:   { g: 'act', hot: true, he: 'פעיל / פעילות', note: 'ACTIVE או ACTIVITY, לפי ההקשר. במרבית ההודעות המקומיות פירושו שיש שם פעילות.' },
  CLSD:  { g: 'act', hot: true, he: 'סגור', note: 'הקיצור הנפוץ ביותר בפיד — הוא מופיע ביותר מחצי מההודעות.' },
  AVBL:  { g: 'act', hot: true, he: 'זמין' },
  'U/S': { g: 'act', he: 'לא שמיש', note: 'Unserviceable. מתקן שקיים אך אינו פועל.' },
  WIP:   { g: 'act', he: 'עבודות בעיצומן', note: 'Work In Progress. הסיבה הנפוצה לסגירת מסלול או שדה.' },
  MAINT: { g: 'act', he: 'אחזקה' },
  WITHDRAWN: { g: 'act', he: 'הוצא משירות' },
  PROH:  { g: 'act', he: 'אסור' },
  PROHIBITED: { g: 'act', he: 'אסור' },
  LTD:   { g: 'act', he: 'מוגבל' },
  RESTRICTED: { g: 'act', he: 'מוגבל' },
  ERECTED: { g: 'act', he: 'הוקם', note: 'בהודעות מכשולים: העגורן כבר עומד שם.' },
  DISMANTLED: { g: 'act', he: 'פורק' },
  ESTABLISHED: { g: 'act', he: 'הוקם / נקבע' },
  NIL:   { g: 'act', he: 'אין', note: 'ברשימת בדיקה: אין הודעות בתוקף בקבוצה הזאת.' },
  CHG:   { g: 'act', he: 'שינוי' },
  CTN:   { g: 'act', hot: true, he: 'זהירות', note: 'כמעט תמיד בצמד CTN ADZ.' },
  ADZ:   { g: 'act', hot: true, he: 'מומלץ', note: 'Advised. הצירוף CTN ADZ פירושו מומלצת זהירות, והוא הביטוי השכיח ביותר בסיום הודעות ישראליות.' },
  'CTN ADZ': { g: 'act', hot: true, he: 'מומלצת זהירות', note: 'עשרות הודעות נחתמות כך. זו אינה אזהרה טקסית: היא נאמרת כשהאזור פתוח אך משהו קורה בו.' },
  EXP:   { g: 'act', he: 'צפוי' },
  DLA:   { g: 'act', he: 'עיכוב' },
  DUE:   { g: 'act', he: 'עקב', note: 'מקדים את הסיבה: DUE WIP, DUE ILS ACT.' },
  EMERG: { g: 'act', he: 'חירום' },
  MEDEVAC: { g: 'act', he: 'פינוי רפואי' },
  FIREFIGHTING: { g: 'act', he: 'כיבוי אש', note: 'סוגר נתיבים ואזורים בהתראה קצרה, בעיקר בקיץ.' },
  'AIR-SHOW': { g: 'act', he: 'מופע אווירי' },
  OPR:   { g: 'act', he: 'מופעל על ידי', note: 'Operated by. בהודעות צניחה: מי נותן את האישור.' },
  PPR:   { g: 'act', hot: true, he: 'נדרש אישור מראש', note: 'Prior Permission Required. בלי טלפון מראש — אין כניסה, גם אם האזור נראה פתוח.' },
  OPS:   { g: 'act', he: 'מבצעים' },

  // --- שדה ומסלול ---
  AD:    { g: 'field', hot: true, he: 'שדה תעופה', note: 'Aerodrome. הצירוף AD CLSD פירושו שהשדה כולו סגור.' },
  ARP:   { g: 'field', he: 'נקודת ייחוס של שדה', note: 'הנקודה שמייצגת את השדה במפות — לא הגבול שלו.' },
  RWY:   { g: 'field', hot: true, he: 'מסלול' },
  TWY:   { g: 'field', he: 'מסלול הסעה' },
  APN:   { g: 'field', he: 'מדרון חניה', note: 'Apron. השטח שבו המטוסים חונים ומטופלים.' },
  TKOF:  { g: 'field', he: 'המראה' },
  LDG:   { g: 'field', he: 'נחיתה' },
  INT:   { g: 'field', he: 'הצטלבות', note: 'Intersection. הצירוף EXC RWY INT פירושו למעט מהצטלבות המסלולים.' },
  OBST:  { g: 'field', he: 'מכשול' },
  CRANE: { g: 'field', he: 'עגורן', note: 'המכשול הזמני הנפוץ ביותר סביב ערים.' },
  AIRSTRIP: { g: 'field', he: 'מנחת' },
  TWR:   { g: 'field', he: 'מגדל פיקוח' },
  APP:   { g: 'field', he: 'בקרת גישה' },
  THR:   { g: 'field', he: 'סף מסלול' },

  // --- ניווט וקשר ---
  ILS:   { g: 'nav', he: 'מערכת נחיתה בהנחיית מכשירים', note: 'אלומות רדיו שמובילות מטוס למסלול בראות ירודה.' },
  VOR:   { g: 'nav', he: 'משואת כיוון' },
  DME:   { g: 'nav', he: 'משואת מרחק' },
  NDB:   { g: 'nav', he: 'משואה לא־כיוונית' },
  GP:    { g: 'nav', he: 'אלומת גובה' },
  LOC:   { g: 'nav', he: 'אלומת כיוון' },
  PAPI:  { g: 'nav', he: 'מחוון זווית גישה' },
  GNSS:  { g: 'nav', he: 'ניווט לוויין' },
  GPS:   { g: 'nav', he: 'ניווט לוויין' },
  RNAV:  { g: 'nav', he: 'ניווט שטח' },
  SID:   { g: 'nav', he: 'נוהל המראה מפורסם' },
  STAR:  { g: 'nav', he: 'נוהל הגעה מפורסם' },
  OCA:   { g: 'nav', he: 'גובה עקיפת מכשולים' },
  FREQ:  { g: 'nav', he: 'תדר' },
  MHZ:   { g: 'nav', he: 'מגה־הרץ', note: 'יחידת התדר. 112.400MHZ הוא ערוץ של משואת ניווט.' },
  'C/S': { g: 'nav', he: 'אות קריאה', note: 'Call Sign. הצירוף שמזהה משואה בשידור מורס.' },
  ATC:   { g: 'nav', hot: true, he: 'פיקוח טיסה' },
  ATS:   { g: 'nav', he: 'שירותי תעבורה אווירית' },
  ATIS:  { g: 'nav', he: 'שידור מידע חוזר לשדה' },

  // --- מי טס שם ---
  ACFT:  { g: 'who', he: 'כלי טיס' },
  FLT:   { g: 'who', hot: true, he: 'טיסה' },
  HEL:   { g: 'who', he: 'מסוק' },
  'UAS/UAV': { g: 'who', hot: true, he: 'כלי טיס בלתי מאויש', note: 'רחפן או מזל"ט. הקבוצה הצומחת ביותר בפיד.' },
  UAS:   { g: 'who', he: 'מערכת כלי טיס בלתי מאויש' },
  UAV:   { g: 'who', he: 'כלי טיס בלתי מאויש' },
  ULTRALIGHT: { g: 'who', he: 'מטוס אולטרלייט', note: 'כלי קל. לרשת האולטרלייט בישראל יש נתיבים ובועות משלה.' },
  BUBBLE:{ g: 'who', hot: true, he: 'בועה', note: 'מונח ישראלי: אזור אימון מקומי לאולטרלייט, בשם ובקוד משלו — למשל BZVUL. אינו מונח ICAO.' },
  CVFR:  { g: 'who', hot: true, he: 'טיסת ראייה מבוקרת', note: 'רשת נתיבי הראייה של ישראל. טיסה בהם מחייבת אישור וקשר.' },
  VFR:   { g: 'who', he: 'טיסת ראייה' },
  IFR:   { g: 'who', he: 'טיסת מכשירים' },
  PJE:   { g: 'who', hot: true, he: 'קפיצות צניחה', note: 'Parachute Jumping Exercise. צנחן נופל מהר ואינו יכול לסטות — האזור נסגר כולו.' },
  MIL:   { g: 'who', he: 'צבאי' },
  TFC:   { g: 'who', he: 'תעבורה' },
  TRG:   { g: 'who', he: 'אימון' },
  AGRICULTURE: { g: 'who', he: 'חקלאי', note: 'טיסת ריסוס. הצירוף INCLUDING AGRICULTURE FLT נאמר במפורש, כי אחרת נוטים להניח שהיא פטורה.' },

  // --- מנהלה ---
  AIP:   { g: 'admin', hot: true, he: 'פרסום מידע תעופתי', note: 'בעברית: פמ"ת. הספר הרשמי שבו כל המגבלות הקבועות.' },
  AIRAC: { g: 'admin', he: 'מחזור עדכון תעופתי', note: 'שינויים בפמ"ת נכנסים לתוקף רק בתאריכי AIRAC — כל 28 יום.' },
  AMDT:  { g: 'admin', he: 'תיקון לפמ"ת' },
  SUP:   { g: 'admin', he: 'תוספת לפמ"ת' },
  ENR:   { g: 'admin', he: 'פרק הנתיבים בפמ"ת' },
  DOM:   { g: 'admin', he: 'פנים־ארצי', note: 'הפמ"ת הפנים־ארצי — הפרסום שרוב הטיסה הפנימית נשענת עליו.' },
  TRIGGER: { g: 'admin', he: 'הודעת הפעלה', note: 'נוטאם שכל תפקידו לבשר שעדכון לפמ"ת נכנס לתוקף. אינו מגבלה בשטח.' },
  CHECKLIST: { g: 'admin', he: 'רשימת בדיקה', note: 'הודעה תקופתית שמונה את מספרי כל הנוטאמים בתוקף, כדי שאפשר יהיה לוודא שלא פוספס אחד.' },
  REF:   { g: 'admin', he: 'ראו' },
  CAT:   { g: 'admin', he: 'קטגוריה' },
  PART:  { g: 'admin', he: 'חלק' },

  // --- מילות קישור ---
  WI:    { g: 'glue', hot: true, he: 'בתוך', note: 'Within. למשל WI 2NM RADIUS — בתוך רדיוס שני מיילים.' },
  BTN:   { g: 'glue', hot: true, he: 'בין', note: 'Between. הצירוף BTN FLW PSN פותח רשימת קודקודים: בין הנקודות הבאות.' },
  FM:    { g: 'glue', hot: true, he: 'מ־', note: 'From. למשל FM GND UP TO 3,700FT — מהקרקע ועד 3,700 רגל.' },
  'UP TO': { g: 'glue', hot: true, he: 'עד' },
  FLW:   { g: 'glue', he: 'הבאים', note: 'Following. אחריו רשימה — נקודות, שעות או תדרים.' },
  EXC:   { g: 'glue', he: 'למעט', note: 'המילה שהופכת סגירה מוחלטת לסגירה חלקית. קל לפספס אותה, ויקר.' },
  INCL:  { g: 'glue', he: 'כולל' },
  INCLUDING: { g: 'glue', he: 'כולל' },
  NR:    { g: 'glue', he: 'מספר', note: 'Number. בהודעות מקומיות, למשל BUBBLE NR B-WEST. בהקשרים אחרים NR הוא גם NEAR, וההקשר מכריע.' },
  BLW:   { g: 'glue', he: 'מתחת' },
  ABV:   { g: 'glue', he: 'מעל' },
  SHALL: { g: 'glue', he: 'חובה ל־' },
};

/* --- פרסור --------------------------------------------------------------
   נמל של scripts/parse_qline.py. הביטויים הרגולריים והחלוקה לפריטים
   זהים בכוונה — הדף הזה חייב להגיע לאותה תוצאה שאליה הגיע הפייתון
   שכתב את data/notams.json, אחרת המפענח מלמד דבר אחד והמפה מראה אחר.

   ההבדל היחיד: פייתון תומך ב-lookbehind ו-Safari הישן לא, ולכן
   ההפרדה לפריטים תופסת גם את התו שלפני האות ומקזזת אותו ביד.
-------------------------------------------------------------------------- */

const ITEM_ORDER = ['Q', 'A', 'B', 'C', 'D', 'E', 'F', 'G'];
const COORD_RE = /^(\d{2})(\d{2})([NS])(\d{3})(\d{2})([EW])(\d{3})$/;
const HEADER_RE = /\b([A-Z]\d{1,4}\/\d{2})\s+(NOTAM[NRC])(?:\s+([A-Z]\d{1,4}\/\d{2}))?/;
const DATE_RE = /^(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$/;
const FIR_WIDE_RADIUS_NM = 999;
const LOW_ALTITUDE_FT = 3000;

/** חותך נוטאם גולמי לפריטים, לפי הסדר הקנוני בלבד. */
function splitItems(raw) {
  const re = /(^|[\s)])([QABCDEFG])\)/g;
  const chosen = [];
  let cursor = 0;
  let lastPos = -1;
  let m;
  while ((m = re.exec(raw)) !== null) {
    const letter = m[2];
    const start = m.index + m[1].length;
    const end = start + 2;
    // פריט מחוץ לסדר הוא כמעט תמיד "B)" שנכתב בתוך טקסט חופשי של E.
    if (ITEM_ORDER.indexOf(letter) < cursor || start < lastPos) continue;
    cursor = ITEM_ORDER.indexOf(letter) + 1;
    lastPos = start;
    chosen.push({ letter, start, end });
  }
  const items = {};
  chosen.forEach((it, i) => {
    const stop = i + 1 < chosen.length ? chosen[i + 1].start : raw.length;
    items[it.letter] = raw.slice(it.end, stop).trim();
  });
  return items;
}

function parseCoordField(field) {
  const m = COORD_RE.exec(String(field).trim().toUpperCase());
  if (!m) throw new Error('שדה מיקום לא תקין: ' + field);
  const [, latD, latM, ns, lonD, lonM, ew, radius] = m;
  if (+latM >= 60 || +lonM >= 60) throw new Error('דקות מחוץ לטווח: ' + field);
  let lat = +latD + +latM / 60;
  let lon = +lonD + +lonM / 60;
  if (ns === 'S') lat = -lat;
  if (ew === 'W') lon = -lon;
  const radiusNm = +radius;
  return {
    lat, lon,
    radius_nm: radiusNm,
    // רדיוס 999 אינו מעגל בן 999 מייל אלא "כל אזור המידע".
    fir_wide: radiusNm === FIR_WIDE_RADIUS_NM,
    raw: String(field).trim().toUpperCase(),
  };
}

function parseAltitudes(lower, upper) {
  lower = String(lower).trim();
  upper = String(upper).trim();
  if (!/^\d+$/.test(lower) || !/^\d+$/.test(upper)) {
    throw new Error('גבהים לא תקינים: ' + lower + '/' + upper);
  }
  return {
    lower_fl: +lower,
    upper_fl: +upper,
    lower_ft: +lower * 100,
    upper_ft: +upper * 100,
    // 000/999 אינו "מ-0 עד 99,900 רגל" אלא "בלי הגבלת גובה".
    unlimited: lower === '000' && upper === '999',
  };
}

function parseLimitItem(text) {
  if (!text) return null;
  const raw = String(text).trim().toUpperCase();
  if (!raw) return null;
  const out = { raw: String(text).trim(), feet: null, reference: null };
  if (/^(SFC|GND|SURFACE|GROUND)/.test(raw)) { out.feet = 0; out.reference = 'AGL'; return out; }
  if (raw.startsWith('UNL')) { out.reference = 'UNLIMITED'; return out; }
  let m = /^FL\s*(\d{2,3})/.exec(raw);
  if (m) { out.feet = +m[1] * 100; out.reference = 'FL'; return out; }
  m = /^(\d+(?:\.\d+)?)\s*(FT|M)\b/.exec(raw);
  if (m) {
    let v = parseFloat(m[1]);
    if (m[2] === 'M') v *= 3.28084;
    out.feet = Math.round(v);
    if (/AGL|GND|SFC/.test(raw)) out.reference = 'AGL';
    else if (/AMSL|MSL/.test(raw)) out.reference = 'AMSL';
    return out;
  }
  return out;
}

function parseQLine(qLine) {
  let text = String(qLine).trim();
  if (text.toUpperCase().startsWith('Q)')) text = text.slice(2).trim();
  const parts = text.split('/').map((p) => p.trim());
  if (parts.length < 8) throw new Error('שורת Q חסרת שדות (' + parts.length + '/8)');
  const [fir, qcodeRaw, traffic, purpose, scope, lower, upper, coord] = parts;
  const qcode = qcodeRaw.toUpperCase();
  if (!/^Q[A-Z]{4}$/.test(qcode)) throw new Error('קוד Q לא תקין: ' + qcode);
  const subject = qcode.slice(1, 3);
  const condition = qcode.slice(3, 5);
  return {
    fir: fir.toUpperCase(),
    q_code: qcode,
    subject_code: subject,
    subject: Q_SUBJECT[subject] || null,
    subject_note: Q_SUBJECT_NOTE[subject] || null,
    condition_code: condition,
    condition: Q_CONDITION[condition] || null,
    traffic: traffic.toUpperCase(),
    purpose: purpose.toUpperCase(),
    scope_code: scope.toUpperCase(),
    scope: Q_SCOPE[scope.toUpperCase()] || null,
    altitude: parseAltitudes(lower, upper),
    geo: parseCoordField(coord),
  };
}

function parseStamp(value) {
  if (!value) return null;
  const raw = String(value).trim().toUpperCase();
  if (!raw) return null;
  const out = { raw: String(value).trim(), iso: null, permanent: false, estimated: false };
  if (raw.startsWith('PERM')) { out.permanent = true; return out; }
  if (/^(WIE|IMMEDIATE|IMM)/.test(raw)) return out;
  if (raw.includes('EST')) out.estimated = true;
  const digits = /(\d{10})/.exec(raw);
  if (!digits) return out;
  const m = DATE_RE.exec(digits[1]);
  const [, yy, mm, dd, hh, mi] = m.map(Number);
  const dt = new Date(Date.UTC(2000 + yy, mm - 1, dd, hh, mi));
  if (isNaN(dt.getTime()) || dt.getUTCMonth() !== mm - 1) return out;
  out.iso = dt.toISOString().replace('.000Z', 'Z');
  return out;
}

/** מפרסר נוטאם גולמי אחד. לעולם אינו זורק — רשומה פגומה חוזרת עם שגיאות. */
function parseNotam(raw) {
  raw = String(raw || '').trim();
  const items = splitItems(raw);
  const rec = {
    id: null, type: null, replaces: null, raw, items,
    locations: [], q: null, geo: null, altitude: null,
    valid_from: null, valid_to: null,
    schedule: items.D || null,
    text: items.E || null,
    lower_limit: parseLimitItem(items.F),
    upper_limit: parseLimitItem(items.G),
    parse_errors: [],
  };

  const header = HEADER_RE.exec(raw);
  if (header) {
    rec.id = header[1];
    rec.type = header[2];
    rec.replaces = header[3] || null;
  } else {
    rec.parse_errors.push('כותרת ההודעה לא זוהתה — חסר מזהה בצורה A1234/26 ואחריו NOTAMN.');
  }
  if (!rec.replaces) {
    const ref = /NOTAM[RC]\s+([A-Z]\d{1,4}\/\d{2})/.exec(raw);
    if (ref) rec.replaces = ref[1];
  }
  if (items.A) rec.locations = items.A.toUpperCase().match(/\b[A-Z]{4}\b/g) || [];

  if (items.Q) {
    try {
      const q = parseQLine(items.Q);
      rec.q = q;
      rec.altitude = q.altitude;
      rec.geo = q.geo;
    } catch (err) {
      rec.parse_errors.push(err.message);
    }
  } else {
    rec.parse_errors.push('שורת Q חסרה.');
  }

  rec.valid_from = parseStamp(items.B);
  rec.valid_to = parseStamp(items.C);
  rec.floor_ft = effectiveFloor(rec);
  rec.low_altitude = rec.floor_ft !== null && rec.floor_ft < LOW_ALTITUDE_FT;
  return rec;
}

/** F) מדויק יותר משורת Q, ולכן הוא גובר עליה. */
function effectiveFloor(rec) {
  if (rec.lower_limit && rec.lower_limit.feet !== null && rec.lower_limit.feet !== undefined) {
    return rec.lower_limit.feet;
  }
  if (rec.altitude && !rec.altitude.unlimited) return rec.altitude.lower_ft;
  if (rec.altitude && rec.altitude.unlimited) return 0;
  return null;
}

/* --- עזרי תצוגה -------------------------------------------------------- */

const el = (id) => document.getElementById(id);

function esc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const localFmt = new Intl.DateTimeFormat('he-IL', {
  timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric',
  hour: '2-digit', minute: '2-digit',
});
const localShortFmt = new Intl.DateTimeFormat('he-IL', {
  timeZone: TZ, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
});
const utcFmt = new Intl.DateTimeFormat('he-IL', {
  timeZone: 'UTC', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
});

function fmtLocal(iso) {
  if (!iso) return '—';
  return localFmt.format(new Date(iso));
}

function fmtLocalShort(iso) {
  if (!iso) return '—';
  return localShortFmt.format(new Date(iso));
}

/*
  מחרוזת לטינית בתוך משפט עברי מתערבבת: "23.08, 03:00Z" נקרא
  "03:00Z ,23.08" ומספר הזמן מחליף מקום עם התאריך. תווי הבידוד
  (FSI…PDI) עוצרים את זה בלי לדרוש עטיפה ב-HTML, כך שהמחרוזת
  נשארת נכונה גם כשהיא נכנסת לטקסט מוברח.
*/
function isolate(text) {
  return '\u2068' + text + '\u2069';
}

function fmtUtc(iso) {
  if (!iso) return '—';
  return isolate(utcFmt.format(new Date(iso)) + 'Z');
}

/** פער השעון בין UTC לישראל ברגע נתון — שלוש שעות בקיץ, שעתיים בחורף. */
function tzOffsetHours(date) {
  const local = new Date(date.toLocaleString('en-US', { timeZone: TZ }));
  const utc = new Date(date.toLocaleString('en-US', { timeZone: 'UTC' }));
  return Math.round((local - utc) / 3600000);
}

function fmtFeet(ft) {
  if (ft === null || ft === undefined) return '—';
  return ft.toLocaleString('he-IL') + ' רגל';
}

/*
  נוטאם עטוף בסוגריים, ולכן הפריט האחרון בהודעה נושא סוגר סוגר
  שאינו חלק מערכו: "3700FT AMSL)". הפרסור שומר אותו כדי להישאר
  זהה לזה שבפייתון — אבל **בהצגה** הוא רק מבלבל, ולכן נחתך כאן,
  ורק כשהוא באמת עודף.
*/
function trimClose(text) {
  const t = String(text || '').trim();
  const open = (t.match(/\(/g) || []).length;
  const close = (t.match(/\)/g) || []).length;
  return close > open && t.endsWith(')') ? t.slice(0, -1).trim() : t;
}

/** טווח הגבהים בשפה אנושית. F)/G) מדויקים משורת Q, ולכן הם קודמים. */
function altitudeText(rec) {
  const lo = rec.lower_limit;
  const hi = rec.upper_limit;
  if (lo || hi) {
    const from = lo ? (lo.feet === 0 ? 'מהקרקע' : 'מ־' + isolate(trimClose(lo.raw))) : 'מ־?';
    const to = hi ? (hi.reference === 'UNLIMITED' ? 'ללא הגבלה' : 'עד ' + isolate(trimClose(hi.raw))) : 'עד ?';
    return from + ' ' + to;
  }
  const alt = rec.altitude;
  if (!alt) return 'לא צוין';
  if (alt.unlimited) return 'כל הגבהים (000/999 — ללא הגבלה)';
  return 'מ־' + fmtFeet(alt.lower_ft) + ' עד ' + fmtFeet(alt.upper_ft);
}

/** קואורדינטה בפורמט קריא לאדם, במעלות ודקות. */
function fmtCoord(geo) {
  if (!geo) return '—';
  const fmtOne = (v, pos, neg) => {
    const dir = v >= 0 ? pos : neg;
    const abs = Math.abs(v);
    const d = Math.floor(abs);
    const m = Math.round((abs - d) * 60);
    return d + '°' + String(m).padStart(2, '0') + '′' + dir;
  };
  return isolate(fmtOne(geo.lat, 'N', 'S') + ' ' + fmtOne(geo.lon, 'E', 'W'));
}

/** האם ההודעה בתוקף ברגע זה. שדה D) אינו נלקח בחשבון — הוא מוצג בנפרד. */
function statusOf(rec, now) {
  now = now || new Date();
  const from = rec.valid_from && rec.valid_from.iso ? new Date(rec.valid_from.iso) : null;
  const to = rec.valid_to && rec.valid_to.iso ? new Date(rec.valid_to.iso) : null;
  const perm = rec.valid_to && rec.valid_to.permanent;
  if (from && from > now) return { key: 'future', label: 'טרם נכנס לתוקף' };
  if (!perm && to && to < now) return { key: 'past', label: 'פג' };
  return { key: 'now', label: 'בתוקף עכשיו' };
}

function durationText(rec) {
  const a = rec.valid_from && rec.valid_from.iso;
  const b = rec.valid_to && rec.valid_to.iso;
  if (rec.valid_to && rec.valid_to.permanent) return 'קבוע — אינו פג';
  if (!a || !b) return '—';
  const mins = Math.round((new Date(b) - new Date(a)) / 60000);
  if (mins < 60) return mins + ' דקות';
  const hours = mins / 60;
  if (hours < 48) return (Math.round(hours * 10) / 10).toLocaleString('he-IL') + ' שעות';
  return Math.round(hours / 24).toLocaleString('he-IL') + ' ימים';
}

/*
  טקסט עברי שמשובצים בו קודים באנגלית — וזה כל ההסברים בעמוד הזה.

  הדפדפן פותר כיוון לפי אלגוריתם דו־כיווני, ותווים "ניטרליים"
  (נקודה, מרכאות, סימן שווה, סוגריים) מקבלים את כיוון השכן. כשקוד
  לטיני יושב בין שני ניטרליים בתוך משפט עברי, הם נגררים איתו
  והתוצאה נקראת הפוך:

      From. "FM GND UP TO 3,700FT" = מהקרקע     ← מה שנכתב
      "From. "FM GND UP TO 3,700FT = מהקרקע     ← מה שנראה

  הפתרון הוא לבודד כל רצף לטיני בתוך תחום כיוון משלו. שני כללים
  שומרים על הפיסוק העברי מחוץ לבידוד: הרצף חייב להיגמר באות או
  בספרה, ומרכאות אינן חלק ממנו לעולם. בלי הכלל השני מרכאה פותחת
  נבלעת פנימה והסוגרת נשארת בחוץ — והציטוט נראה שבור בדיוק כמו
  קודם, רק במקום אחר.
*/
const LATIN_RUN_RE = /[A-Za-z0-9][A-Za-z0-9 .,:;\/()+\u2013\u2014-]*[A-Za-z0-9]|[A-Za-z0-9]/g;

function richText(value) {
  const source = String(value == null ? '' : value);
  let out = '';
  let idx = 0;
  let m;
  LATIN_RUN_RE.lastIndex = 0;
  while ((m = LATIN_RUN_RE.exec(source)) !== null) {
    out += esc(source.slice(idx, m.index));
    out += '<span class="ltr">' + esc(m[0]) + '</span>';
    idx = m.index + m[0].length;
  }
  return out + esc(source.slice(idx));
}

/* --- הדגשת קיצורים בתוך טקסט ------------------------------------------ */

/*
  הטקסט של פריט E) הוא המקום שבו נשברים. הדגשת הקיצורים הופכת אותו
  ממחרוזת אטומה לטקסט שאפשר לחקור: כל קיצור מוכר הוא כפתור, ולחיצה
  עליו אומרת מה הוא. הצירופים הארוכים נבדקים ראשונים, אחרת "CTN"
  היה בולע את "CTN ADZ".
*/
const ABBR_KEYS = Object.keys(ABBR).sort((a, b) => b.length - a.length);
const ABBR_TOKEN_RE = ABBR_KEYS.map((k) => k.replace(/[/\-]/g, '\\$&')).join('|');

/*
  בלי lookbehind בכוונה. הביטוי `(?<!...)` נתמך רק בדפדפנים חדשים,
  ו-`new RegExp` איתו **זורק** במקום להיכשל בשקט — כלומר עמוד שלם
  שלא נטען בטלפון ישן. גבולות המילה נבדקים ביד, שתי שורות, בטוח.
*/
function markAbbreviations(text) {
  if (!text) return '';
  const source = String(text);
  let out = '';
  let idx = 0;
  const re = new RegExp('(' + ABBR_TOKEN_RE + ')', 'g');
  let m;
  while ((m = re.exec(source)) !== null) {
    const before = source[m.index - 1];
    const after = source[m.index + m[0].length];
    const boundary = (c) => c === undefined || !/[A-Z0-9]/.test(c);
    if (!boundary(before) || !boundary(after)) continue;
    out += esc(source.slice(idx, m.index));
    out += '<button type="button" class="abbr" data-abbr="' + esc(m[0]) + '">' + esc(m[0]) + '</button>';
    idx = m.index + m[0].length;
  }
  out += esc(source.slice(idx));
  return out;
}

/* --- נתונים ------------------------------------------------------------- */

/*
  הפיד החי הוא חומר הלימוד. דוגמה מומצאת מלמדת לקרוא דוגמאות
  מומצאות; הודעה אמיתית מהיום מלמדת לקרוא את מה שבאמת מתפרסם כאן.

  אם הטעינה נכשלת — קובץ חסר, פתיחה מהדיסק, אין רשת — הדף לא נשבר:
  הוא נופל לדוגמאות המוטבעות, מודיע על כך בשקט, וכל שאר המסכים
  ממשיכים לעבוד. שיעור שלא נטען הוא שיעור שלא נלמד.
*/
const state = {
  feed: [],          // נוטאמים מהפיד, כפי שנכתבו על ידי הפרסור בפייתון
  feedOk: false,
  generatedAt: null,
  fieldNames: new Map(),   // קוד ICAO -> שם עברי
};

async function loadFeed() {
  try {
    const res = await fetch(FEED_URL, { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    state.feed = Array.isArray(data.notams) ? data.notams : [];
    state.generatedAt = data.generated_at || null;
    state.feedOk = state.feed.length > 0;
  } catch (err) {
    state.feedOk = false;
  }
}

async function loadFieldNames() {
  try {
    const res = await fetch(FIELDS_URL, { cache: 'no-store' });
    if (!res.ok) return;
    const data = await res.json();
    (data.features || []).forEach((f) => {
      const p = f.properties || {};
      if (p.icao && p.name && !state.fieldNames.has(p.icao)) state.fieldNames.set(p.icao, p.name);
    });
  } catch (err) { /* שמות השדות הם קישוט, לא תנאי */ }
}

function fieldName(icao) {
  if (icao === 'LLLL') return 'כל מרחב תל אביב';
  return state.fieldNames.get(icao) || null;
}

/* --- הפענוח המשותף ------------------------------------------------------
   גם המפרק וגם המפענח מציגים את אותו דבר: הודעה אחת, פרוקה לשדותיה.
   ההבדל היחיד הוא מאיפה מגיע הטקסט. לכן יש כאן פונקציה אחת, ולא שתי
   גרסאות שיסטו זו מזו אחרי חודשיים.
-------------------------------------------------------------------------- */

/** חמש התשובות שכל טייס מחפש — בסדר שבו כדאי לחפש אותן. */
function fiveAnswers(rec) {
  const q = rec.q;
  const rows = [];

  // מה
  let what = q && q.subject ? q.subject : null;
  if (q && q.condition) what = what ? what + ' — ' + q.condition : q.condition;
  if (!what && q) what = 'קוד ' + q.q_code + ' — אין תווית מאומתת. קראו את פריט E.';
  rows.push({ k: 'מה קורה', v: what || 'לא ניתן לקבוע בלי שורת Q — קראו את פריט E.' });

  // איפה
  const where = [];
  if (rec.locations.length) {
    where.push(rec.locations.map((c) => {
      const name = fieldName(c);
      return name ? c + ' (' + name + ')' : c;
    }).join(', '));
  }
  if (rec.geo) {
    if (rec.geo.fir_wide) where.push('רדיוס 999 — כל אזור המידע, לא מעגל');
    else where.push('מעגל ברדיוס ' + rec.geo.radius_nm + ' מייל ימי סביב ' + fmtCoord(rec.geo));
  }
  rows.push({ k: 'איפה', v: where.join(' · ') || 'לא צוין' });

  // מתי
  const st = statusOf(rec);
  let when;
  if (rec.valid_from && rec.valid_from.iso) {
    when = fmtLocal(rec.valid_from.iso) + ' עד ' +
      (rec.valid_to && rec.valid_to.permanent ? 'קבוע' : fmtLocal(rec.valid_to && rec.valid_to.iso));
  } else if (rec.valid_from) {
    when = rec.valid_from.raw;
  } else {
    when = 'לא צוין';
  }
  // B ו-C הומרו לשעון ישראל, אבל D) נשאר כלשונו — והוא UTC.
  // בלי המילה הזאת השורה מציגה שני שעונים שונים כאילו הם אחד.
  if (rec.schedule) when += ' — אך רק בשעות (UTC): ' + isolate(trimClose(rec.schedule));
  rows.push({ k: 'מתי', v: when, status: st });

  // גובה
  rows.push({ k: 'מאיזה גובה', v: altitudeText(rec) });

  // למי
  const who = [];
  if (rec.q) {
    if (Q_TRAFFIC[rec.q.traffic]) who.push(Q_TRAFFIC[rec.q.traffic]);
    const purposes = rec.q.purpose.split('').map((c) => Q_PURPOSE[c]).filter(Boolean);
    if (purposes.length) who.push(purposes.join('; '));
  }
  rows.push({ k: 'למי זה נוגע', v: who.join(' · ') || 'לא צוין' });

  return rows;
}

/** שורת Q, שמונת שדותיה, כל אחד עם ערכו ומשמעותו. */
function qLineRows(q) {
  if (!q) return [];
  const purposeText = q.purpose.split('')
    .map((c) => (Q_PURPOSE[c] ? c + ' = ' + Q_PURPOSE[c] : c + ' = לא מזוהה'))
    .join(' · ');
  const alt = q.altitude.unlimited
    ? 'ללא הגבלת גובה — 000/999 אינו "מ-0 עד 99,900 רגל"'
    : fmtFeet(q.altitude.lower_ft) + ' עד ' + fmtFeet(q.altitude.upper_ft);
  const geo = q.geo.fir_wide
    ? fmtCoord(q.geo) + ', רדיוס 999 = כל אזור המידע'
    : fmtCoord(q.geo) + ', רדיוס ' + q.geo.radius_nm + ' מייל ימי';
  return [
    { n: 1, name: 'אזור מידע טיסה', raw: q.fir, mean: q.fir === 'LLLL' ? 'מרחב תל אביב' : 'קוד FIR' },
    {
      n: 2, name: 'קוד הנושא והמצב', raw: q.q_code,
      mean: (q.subject || 'נושא ' + q.subject_code + ' — אין תווית מאומתת') + ' · ' +
        (q.condition || 'מצב ' + q.condition_code + ' — אין תווית מאומתת'),
    },
    { n: 3, name: 'למי', raw: q.traffic, mean: Q_TRAFFIC[q.traffic] || 'צירוף לא מזוהה' },
    { n: 4, name: 'לאיזו מטרה', raw: q.purpose, mean: purposeText },
    { n: 5, name: 'היקף', raw: q.scope_code, mean: Q_SCOPE[q.scope_code] || 'צירוף לא מזוהה' },
    { n: 6, name: 'רצפה', raw: String(q.altitude.lower_fl).padStart(3, '0'), mean: alt },
    { n: 7, name: 'תקרה', raw: String(q.altitude.upper_fl).padStart(3, '0'), mean: '(נקרא יחד עם שדה 6)' },
    { n: 8, name: 'מרכז ורדיוס', raw: q.geo.raw || '', mean: geo },
  ];
}

/** מה שכל פריט מכיל בהודעה **הזאת**, להבדיל ממה שהפריט הוא בכלל. */
function itemMeaning(letter, rec) {
  const v = rec.items[letter];
  switch (letter) {
    case 'HEAD': {
      const parts = [];
      if (rec.id) {
        // השנה במזהה היא דו־ספרתית ("/26"), ו"שנת 26" אינו אומר דבר.
        parts.push('הודעה ' + rec.id.split('/')[0].slice(1) + ' בסדרה ' +
          rec.id[0] + ', שנת 20' + rec.id.split('/')[1] + '.');
      }
      const t = NOTAM_TYPE[rec.type];
      if (t) parts.push(rec.type + ' — ' + t.label + '. ' + t.note);
      if (rec.replaces) parts.push('ההודעה שהיא מחליפה: ' + rec.replaces + '.');
      return parts.join(' ') || 'לא זוהתה כותרת.';
    }
    case 'Q':
      return rec.q ? 'שמונה שדות, מפורטים בטבלה.' : 'שורת Q שלא נפרסרה: ' + (rec.parse_errors[0] || '');
    case 'A': {
      const named = rec.locations.map((c) => {
        const n = fieldName(c);
        return n ? c + ' — ' + n : c;
      });
      return named.join(' · ') || v;
    }
    case 'B': {
      if (!rec.valid_from) return v;
      if (rec.valid_from.iso) return fmtLocal(rec.valid_from.iso) + ' שעון ישראל (' + fmtUtc(rec.valid_from.iso) + ')';
      return rec.valid_from.raw + ' — כניסה מיידית לתוקף';
    }
    case 'C': {
      if (!rec.valid_to) return v;
      if (rec.valid_to.permanent) return 'קבוע — ההודעה אינה פגה מעצמה';
      if (rec.valid_to.iso) {
        return fmtLocal(rec.valid_to.iso) + ' שעון ישראל (' + fmtUtc(rec.valid_to.iso) + ')' +
          (rec.valid_to.estimated ? ' — EST, כלומר הערכה בלבד' : '');
      }
      return rec.valid_to.raw;
    }
    case 'D':
      return 'ההודעה פעילה רק בשעות האלה (UTC), בתוך החלון של B ו-C.';
    case 'E':
      return 'הנוסח המלא. הקודים לא נושאים את הפרטים — הם כאן.';
    case 'F': {
      const l = rec.lower_limit;
      if (!l) return v;
      if (l.feet === 0) return 'רצפה בקרקע — אין מרווח מתחת.';
      return l.feet !== null ? 'רצפה: ' + fmtFeet(l.feet) + (l.reference ? ' (' + l.reference + ')' : '') : trimClose(v);
    }
    case 'G': {
      const u = rec.upper_limit;
      if (!u) return v;
      if (u.reference === 'UNLIMITED') return 'תקרה: ללא הגבלה — אי אפשר לעבור מעל.';
      return u.feet !== null ? 'תקרה: ' + fmtFeet(u.feet) + (u.reference ? ' (' + u.reference + ')' : '') : trimClose(v);
    }
    default:
      return v;
  }
}

function statusBadge(st) {
  const cls = { now: 'badge--now', future: 'badge--future', past: 'badge--past' }[st.key];
  return '<span class="badge ' + cls + '">' + esc(st.label) + '</span>';
}

/** הפענוח המלא של הודעה אחת. `opts.collapsed` פותח את הפריטים סגורים. */
function renderBreakdown(rec, opts) {
  opts = opts || {};
  const st = statusOf(rec);
  const type = NOTAM_TYPE[rec.type];
  let html = '<div class="brk">';

  html += '<div class="brk__head">';
  html += '<span class="brk__id">' + esc(rec.id || 'ללא מזהה') + '</span>';
  if (type) html += '<span class="badge badge--type" title="' + esc(type.note) + '">' + esc(type.label) + '</span>';
  html += statusBadge(st);
  if (rec.replaces) html += '<span class="badge badge--rep">מחליפה את ' + esc(rec.replaces) + '</span>';
  html += '</div>';

  if (rec.parse_errors.length) {
    html += '<p class="brk__err">' + rec.parse_errors.map(esc).join(' ') + '</p>';
  }

  html += '<dl class="five">';
  fiveAnswers(rec).forEach((row) => {
    html += '<dt>' + esc(row.k) + '</dt><dd>' + richText(row.v) + '</dd>';
  });
  html += '</dl>';

  // הפריטים עצמם — הטקסט המקורי לצד המשמעות, תמיד זה מול זה.
  html += '<h4 class="brk__sub">שדה אחרי שדה</h4><ol class="fields">';
  ITEM_ORDER.forEach((letter) => {
    const raw = rec.items[letter];
    if (!raw) return;
    const info = ITEM_INFO[letter];
    html += '<li class="field">';
    html += '<div class="field__head"><span class="field__letter">' + letter + ')</span>';
    html += '<span class="field__name">' + esc(info.short) + '</span></div>';
    html += '<pre class="field__raw">' + (letter === 'E' ? markAbbreviations(raw) : esc(raw)) + '</pre>';
    html += '<p class="field__mean">' + richText(itemMeaning(letter, rec)) + '</p>';
    html += '<p class="field__about">' + richText(info.text) + '</p>';
    html += '</li>';
  });
  html += '</ol>';

  if (rec.q) {
    html += '<h4 class="brk__sub">שורת Q, שדה־שדה</h4>';
    html += '<div class="qtable-wrap"><table class="qtable"><thead><tr>' +
      '<th>#</th><th>שדה</th><th>הערך</th><th>מה זה אומר</th></tr></thead><tbody>';
    qLineRows(rec.q).forEach((r) => {
      html += '<tr><td class="qtable__n">' + r.n + '</td><td>' + esc(r.name) + '</td>' +
        '<td class="mono">' + esc(r.raw) + '</td><td>' + richText(r.mean) + '</td></tr>';
    });
    html += '</tbody></table></div>';
    if (rec.q.subject_note) {
      html += '<p class="brk__note">' + richText(rec.q.subject_note) + '</p>';
    }
  }

  html += '<details class="raw"><summary>הטקסט המקורי, בלי נגיעה</summary><pre>' +
    esc(rec.raw) + '</pre></details>';
  html += '</div>';
  return html;
}

/* --- לשוניות ----------------------------------------------------------- */

/*
  לשוניות ולא גלילה אחת ארוכה: שבעה מסכים שכל אחד מהם הוא דרך לימוד
  אחרת, ואף אחד מהם אינו תלוי בקודמו. הכתובת נושאת את הלשונית הפעילה
  (`#quiz`), כדי שאפשר יהיה לשלוח קישור ישר לתרגול, וכדי שכפתור
  "אחורה" של הדפדפן יעשה את מה שמצפים ממנו.
*/
function initTabs() {
  const tabs = Array.from(document.querySelectorAll('.tab'));
  const panels = Array.from(document.querySelectorAll('.panel'));
  if (!tabs.length) return;

  function show(name, push) {
    const found = tabs.some((t) => t.dataset.tab === name);
    if (!found) name = tabs[0].dataset.tab;
    tabs.forEach((t) => {
      const on = t.dataset.tab === name;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
    });
    panels.forEach((p) => { p.hidden = p.dataset.panel !== name; });
    // הרצועה גוללת לרוחב במסך צר; לשונית שנבחרה מהכתובת עלולה
    // לשבת מחוץ לתצוגה, ואז נראה כאילו שום דבר לא קרה.
    const active = tabs.find((t) => t.dataset.tab === name);
    if (active) active.scrollIntoView({ block: 'nearest', inline: 'center' });
    if (push && location.hash.slice(1) !== name) history.replaceState(null, '', '#' + name);
  }

  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => {
      show(tab.dataset.tab, true);
      // המשתמש בחר מסך — הוא צריך לראות את ראשו, לא את אמצעו.
      document.querySelector('.tabs').scrollIntoView({ block: 'start' });
    });
    // חצים בין לשוניות, כמצופה מ-tablist נגיש. ב-RTL הכיוונים הפוכים.
    tab.addEventListener('keydown', (ev) => {
      const step = ev.key === 'ArrowLeft' ? 1 : ev.key === 'ArrowRight' ? -1 : 0;
      if (!step) return;
      ev.preventDefault();
      const next = tabs[(i + step + tabs.length) % tabs.length];
      next.focus();
      show(next.dataset.tab, true);
    });
  });

  show(location.hash.slice(1) || tabs[0].dataset.tab, false);
  window.addEventListener('hashchange', () => show(location.hash.slice(1), false));
}

/* --- מסך 2: המפרק ------------------------------------------------------ */

/*
  תשע הודעות אמיתיות, מסודרות מהפשוטה למורכבת, שכל אחת מלמדת דבר
  אחד שהקודמת לא. הן מוקפאות בקוד ולא נמשכות מהפיד בכוונה: שיעור
  חייב להיות יציב, ואי אפשר ללמד "שימו לב ל-D)" על הודעה שהתחלפה
  בינתיים באחרת שאין לה D). הפיד החי משמש במסכים האחרים.
*/
const EXAMPLES = [
  {
    label: 'שדה סגור',
    why: 'הפשוטה ביותר שתמצאו: ארבעה פריטים, משפט אחד. אם אתם יודעים לקרוא אותה — יש לכם את השלד.',
    raw: '(A0354/26 NOTAMN\nQ) LLLL/QFALC/IV/NBO/A /000/999/3201N03453E005\nA) LLBG B) 2610161500 C) 2610161955\nE) AD CLSD DUE WIP.)',
  },
  {
    label: 'סגירה בשעות',
    why: 'אותה הודעה, עם פריט D). בלעדיו נראה שהשדה סגור ברצף חמש שעות; איתו — שתי חלונות נפרדים.',
    raw: '(A0663/26 NOTAMN\nQ) LLLL/QFALC/IV/NBO/A /000/999/3249N03503E005\nA) LLHA B) 2609010525 C) 2609011000\nD) 0525-0725 0830-1000\nE) AD CLSD TO ALL FLT INCLUDING HEL, DUE WIP.\nIN CASE OF EMERG AVBL WI 10MIN.)',
  },
  {
    label: 'רחפן',
    why: 'הקבוצה הצומחת בפיד. שימו לב שהיא נוקבת בשני גבהים שונים — 600 מטר מעל הקרקע לפעילות, ו-3,700 רגל מעל פני הים לסגירה.',
    raw: '(C1764/26 NOTAMN\nQ) LLLL/QWULW/IV/BO /W /000/037/3058N03456E001\nA) LLLL B) 2608230300 C) 2608271430\nD) DAILY 0300-1430\nE) UAS/UAV ACT WILL TAKE PLACE AT YERUHAM, FM GND UP TO 600M AGL.\nAN AREA WI 0.3NM RADIUS CENTERED ON PSN 305819N0345601E\nCLSD FM GND UP TO 3,700FT AMSL.\nCTN ADZ.\nF) GND G) 3700FT AMSL)',
  },
  {
    label: 'כדור פורח',
    why: 'לוח זמנים שחוצה חצות: "1700-0200" אינו טעות אלא לילה אחד. וגם — הכבל, לא הבלון, הוא מה שמסוכן.',
    raw: '(C1719/26 NOTAMN\nQ) LLLL/QWCLW/IV/M /W /000/018/3306N03535E001\nA) LLLL B) 2608160330 C) 2608230200\nD) DAILY 0330-1400 1700-0200\nE) CAPTIVE BALLOON WILL TAKE PLACE AT HACHULA-LAKE,\nFM GND UP TO 400M AGL. LIT AND DAY MARKED.\nAN AREA WI 0.54NM RADIUS CENTERED ON PSN 330622N0353454E\nCLSD FM GND UP TO 1,800FT AMSL, TO ALL FLT INCLUDING\nAGRICULTURE FLT.\nCTN ADZ.\nF) GND G) 1800FT AMSL)',
  },
  {
    label: 'עגורן',
    why: 'הודעה שהגבול שלה כתוב בגוף הטקסט: ארבע נקודות ציון, ולא המעגל שבשורת Q. כשיש רשימת קודקודים — היא הגובר.',
    raw: '(A0666/26 NOTAMN\nQ) LLLL/QOBCE/IV/M /AE/000/004/3159N03454E001\nA) LLBG B) 2608190300 C) 2608190900\nE) CRANE ERECTED WI LLBG CTR, AT EL-AL JUNCTION.\nAN AREA FM GND UP TO 100M 360FT AMSL CLSD BTN FLW PSN\n315924N0345425E 315922N0345423E 315924N0345419E\n315926N0345421E.\nCTN ADZ.)',
  },
  {
    label: 'נתיב סגור',
    why: 'כאן אין קואורדינטות בכלל — יש שמות של נקודות דיווח. מי שאינו מכיר את הרשת לא יידע איפה זה, וזו בדיוק הנקודה: פריט E) מניח ידע.',
    raw: '(C1755/26 NOTAMN\nQ) LLLL/QARLC/IV/NBO/E /025/030/3235N03513E013\nA) LLLL B) 2608190715 C) 2608191050\nD) 0715-0740 1030-1050\nE) CVFR RTE CLSD DUE ILS ACT WI LLRD\nEIRON-ZMGID-AFULA-TAVOR.\nAFULA-EITAN.)',
  },
  {
    label: 'שיבוש GPS',
    why: 'הודעה מסוג R — היא מחליפה הודעה קודמת, ומזהה המוחלפת כתוב מיד אחרי NOTAMR. גם: רדיוס 117 מייל, כלומר כמעט כל המרחב.',
    raw: '(A0596/26 NOTAMR A0508/26\nQ) LLLL/QGWAU/IV/NBO/E /000/999/3125N03521E117\nA) LLLL B) 2607281045 C) 2608312359\nE) POSS INTRP TO AIRBORNE GNSS EQPT WI TEL-AVIV FIR.)',
  },
  {
    label: 'אזור קבוע',
    why: 'C) PERM — הודעה שאינה פגה. וגם: הגבהים בפריטי F/G שונים מאלה שבשורת Q, והמפורשים גוברים.',
    raw: '(A0616/26 NOTAMN\nQ) LLLL/QRRCA/IV/BO /W /070/400/3247N03441E022\nA) LLLL B) 2608061630 C) PERM\nE) LLR01 ACTIVATED H24, XNG MERVA NOT AVBL EXC BY ATC.\nTFC TO/FM LLHA AVBL VIA MERVA BIDIRECTIONAL AT 5,000FT AMSL.\nISRAEL AIP, PART ENR 5.1, PAGE ENR 5.1-3, PARA 2,\nCHART ENR 6-1 REF.\nF) 7000FT AMSL G) 40000FT AMSL)',
  },
  {
    label: 'הודעה שאינה מגבלה',
    why: 'TRIGGER NOTAM אינו סוגר דבר: הוא רק מודיע שעדכון לפמ"ת נכנס לתוקף. מי שלא מזהה את הסוג הזה מבזבז זמן על הודעות שאינן נוגעות לטיסה.',
    raw: '(C1678/26 NOTAMN\nQ) LLLL/QOATT/IV/BO /E /000/999/3211N03515E015\nA) LLLL B) 2609030001 C) 2609162359\nE) TRIGGER NOTAM - NIL AIRAC DOM AIP AMDT WEF 03 SEP 2026.)',
  },
];

function initDissector() {
  const picker = el('ex-picker');
  const why = el('ex-why');
  const segsBox = el('ex-segs');
  const explain = el('ex-explain');
  const full = el('ex-full');
  if (!picker) return;

  let current = 0;
  let rec = null;

  picker.innerHTML = EXAMPLES.map((ex, i) =>
    '<button type="button" class="chip" data-i="' + i + '" aria-pressed="' + (i === 0) + '">' +
    esc(ex.label) + '</button>').join('');

  function renderSegments() {
    // הטקסט המקורי, חתוך לפריטים — כל פריט כפתור. זו ההמחשה שהנוטאם
    // אינו פסקה אלא טופס: מה שנראה כמו ג'יבריש הוא שמונה תאים.
    const parts = [];
    const raw = rec.raw;
    let cursor = 0;
    const marks = [];
    const re = /(^|[\s)])([QABCDEFG])\)/g;
    let m, order = 0, last = -1;
    while ((m = re.exec(raw)) !== null) {
      const letter = m[2];
      const start = m.index + m[1].length;
      if (ITEM_ORDER.indexOf(letter) < order || start < last) continue;
      order = ITEM_ORDER.indexOf(letter) + 1;
      last = start;
      marks.push({ letter, start });
    }
    marks.forEach((mk, i) => {
      const stop = i + 1 < marks.length ? marks[i + 1].start : raw.length;
      if (mk.start > cursor) {
        // הקטע שלפני הפריט הראשון הוא הכותרת. הוא לחיץ כמו השאר,
        // וכל קטע ביניים אחר נשאר טקסט פשוט.
        const cls = i === 0 ? 'seg' : 'seg seg--plain';
        const attr = i === 0 ? ' data-letter="HEAD"' : '';
        const tag = i === 0 ? 'button' : 'span';
        parts.push('<' + tag + ' type="button" class="' + cls + '"' + attr + '>' +
          esc(raw.slice(cursor, mk.start)) + '</' + tag + '>');
      }
      parts.push('<button type="button" class="seg" data-letter="' + mk.letter + '">' +
        esc(raw.slice(mk.start, stop)) + '</button>');
      cursor = stop;
    });
    if (cursor < raw.length) parts.push('<span class="seg seg--plain">' + esc(raw.slice(cursor)) + '</span>');
    segsBox.innerHTML = parts.join('');
  }

  function select(letter) {
    const info = ITEM_INFO[letter];
    if (!info) return;
    segsBox.querySelectorAll('.seg[data-letter]').forEach((b) => {
      b.classList.toggle('seg--on', b.dataset.letter === letter);
    });
    const chip = letter === 'HEAD' ? '' :
      '<span class="field__letter">' + letter + ')</span> ';
    let html =
      '<h3 class="explain__title">' + chip + esc(info.name) +
      ' — ' + esc(info.short) + '</h3>' +
      '<p class="explain__about">' + richText(info.text) + '</p>';
    // שורת Q היא היחידה שאי אפשר להסביר במשפט: היא שמונה שדות,
    // וההפניה ל"טבלה שלמטה" שולחת את הלומד לחפש במקום ללמד.
    if (letter === 'Q' && rec.q) {
      html += '<div class="qtable-wrap"><table class="qtable"><thead><tr>' +
        '<th>#</th><th>שדה</th><th>הערך</th><th>מה זה אומר</th></tr></thead><tbody>';
      qLineRows(rec.q).forEach((r) => {
        html += '<tr><td class="qtable__n">' + r.n + '</td><td>' + esc(r.name) + '</td>' +
          '<td class="mono">' + esc(r.raw) + '</td><td>' + richText(r.mean) + '</td></tr>';
      });
      html += '</tbody></table></div>';
    } else {
      html += '<p class="explain__here"><strong>בהודעה הזאת:</strong> ' +
        richText(itemMeaning(letter, rec)) + '</p>';
    }
    explain.innerHTML = html;
  }

  function load(i) {
    current = i;
    const ex = EXAMPLES[i];
    rec = parseNotam(ex.raw);
    picker.querySelectorAll('.chip').forEach((c) => {
      c.setAttribute('aria-pressed', String(+c.dataset.i === i));
    });
    why.textContent = ex.why;
    renderSegments();
    explain.innerHTML = '<p class="explain__hint">לחצו על כל חלק בהודעה שלמעלה כדי לראות מה הוא אומר.</p>';
    full.innerHTML = renderBreakdown(rec);
    const det = full.closest('details');
    if (det) det.open = false;
  }

  picker.addEventListener('click', (ev) => {
    const btn = ev.target.closest('.chip');
    if (btn) load(+btn.dataset.i);
  });
  segsBox.addEventListener('click', (ev) => {
    const btn = ev.target.closest('.seg[data-letter]');
    if (btn) select(btn.dataset.letter);
  });
  el('ex-next').addEventListener('click', () => load((current + 1) % EXAMPLES.length));
  el('ex-prev').addEventListener('click', () => load((current - 1 + EXAMPLES.length) % EXAMPLES.length));

  load(0);
}

/* --- מסך 3: המפענח ----------------------------------------------------- */

/*
  הדבקה של הודעה כלשהי — מהתדריך, מהוואטסאפ של המועדון, מכל מקום —
  ופענוח מלא שלה. זה המסך שהופך את העמוד מקריאה לכלי.

  הפענוח רץ אצל המשתמש בלבד. שום דבר ממה שמודבק כאן אינו נשלח לשום
  מקום, כי אין לאן: לדף אין שרת.
*/
function initDecoder() {
  const input = el('dec-input');
  const out = el('dec-out');
  if (!input) return;

  function run() {
    const raw = input.value.trim();
    // תיבה ריקה אינה שגיאה ואינה מצריכה הודעה: ההוראה כתובה בתוך
    // התיבה עצמה, במקום שבו באמת מדביקים.
    if (!raw) {
      out.innerHTML = '';
      return;
    }
    const rec = parseNotam(raw);
    // הודעה שאין בה שום פריט מזוהה כמעט תמיד אינה נוטאם אלא טקסט אחר.
    if (!Object.keys(rec.items).length) {
      out.innerHTML = '<p class="empty">לא זוהו פריטים בצורה <span class="mono">Q) A) B) C) E)</span>. ' +
        'ודאו שהעתקתם את ההודעה כולה, כולל שורת ה-Q.</p>';
      return;
    }
    out.innerHTML = renderBreakdown(rec);
  }

  el('dec-run').addEventListener('click', run);
  el('dec-clear').addEventListener('click', () => {
    input.value = '';
    run();
    input.focus();
  });
  el('dec-sample').addEventListener('click', () => {
    // הודעה אקראית מהפיד של היום. אם הפיד לא נטען — דוגמה מוקפאת.
    const pool = state.feedOk ? state.feed : EXAMPLES;
    const pick = pool[Math.floor(Math.random() * pool.length)];
    input.value = pick.raw;
    run();
  });
  // Ctrl+Enter מפענח, כמו בכל תיבת טקסט שיש בה כפתור שליחה.
  input.addEventListener('keydown', (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter') run();
  });

  run();
}

/* --- מסך 4: קוד Q ------------------------------------------------------- */

/*
  בונה קוד: בוחרים נושא ומצב, ומקבלים את חמש האותיות ואת פירושן.
  זה הפוך מהדרך הרגילה — בדרך כלל רואים קוד ומחפשים מה הוא — וזו
  בדיוק הסיבה שזה עובד: כדי לבנות QWULW צריך להבין למה W, למה U
  ולמה LW.

  לצדו הטבלה המלאה, מסומנת במה שמופיע בפיד **ברגע זה**. הסימון נעשה
  מתוך הנתונים ולא מתוך רשימה כתובה — טבלה שמספרת על עצמה שהיא
  מעודכנת אינה מעודכנת.
*/
function initQCodes() {
  const subjSel = el('q-subject');
  const condSel = el('q-condition');
  const outBox = el('q-out');
  const tableBox = el('q-table');
  const search = el('q-search');
  if (!subjSel) return;

  // ספירת השימוש בפועל, לפי קוד.
  const useSubject = new Map();
  const useCondition = new Map();
  const sample = new Map();
  state.feed.forEach((n) => {
    if (!n.q) return;
    useSubject.set(n.q.subject_code, (useSubject.get(n.q.subject_code) || 0) + 1);
    useCondition.set(n.q.condition_code, (useCondition.get(n.q.condition_code) || 0) + 1);
    if (!sample.has(n.q.q_code)) sample.set(n.q.q_code, n);
  });

  const subjects = Object.keys(Q_SUBJECT).sort();
  const conditions = Object.keys(Q_CONDITION).sort();

  subjSel.innerHTML = subjects.map((c) =>
    '<option value="' + c + '">' + c + ' — ' + esc(Q_SUBJECT[c]) + '</option>').join('');
  condSel.innerHTML = conditions.map((c) =>
    '<option value="' + c + '">' + c + ' — ' + esc(Q_CONDITION[c]) + '</option>').join('');
  subjSel.value = 'WU';
  condSel.value = 'LW';

  function build() {
    const s = subjSel.value;
    const c = condSel.value;
    const code = 'Q' + s + c;
    const family = Q_FAMILY[s[0]];
    const seen = sample.get(code);
    let html = '<p class="qbuild__code mono">' + code + '</p>';
    html += '<dl class="five">';
    html += '<dt>Q</dt><dd>תמיד. זו רק הפתיחה.</dd>';
    html += '<dt>' + s + '</dt><dd>' + esc(Q_SUBJECT[s]) +
      (family ? ' <span class="muted">— משפחת ' + esc(s[0]) + ': ' + esc(family) + '</span>' : '') + '</dd>';
    html += '<dt>' + c + '</dt><dd>' + esc(Q_CONDITION[c]) + '</dd>';
    html += '</dl>';
    if (Q_SUBJECT_NOTE[s]) html += '<p class="brk__note">' + richText(Q_SUBJECT_NOTE[s]) + '</p>';
    html += '<p class="qbuild__read"><strong>קוראים את זה כך:</strong> ' +
      esc(Q_SUBJECT[s]) + ' — ' + esc(Q_CONDITION[c]) + '.</p>';
    if (seen) {
      html += '<p class="qbuild__seen">הצירוף הזה מופיע בפיד עכשיו, למשל ב־<span class="mono">' +
        esc(seen.id) + '</span>:</p><pre class="field__raw">' + esc((seen.text || '').split('\n')[0]) + '</pre>';
    } else if (state.feedOk) {
      html += '<p class="qbuild__seen muted">הצירוף הזה אינו מופיע בפיד ברגע זה. הוא עדיין תקין — פשוט לא קורה כרגע.</p>';
    }
    outBox.innerHTML = html;
  }

  function renderTable() {
    const term = (search.value || '').trim().toLowerCase();
    const rows = [];
    subjects.forEach((code) => {
      const label = Q_SUBJECT[code];
      const note = Q_SUBJECT_NOTE[code] || '';
      const hay = (code + ' ' + label + ' ' + note).toLowerCase();
      if (term && hay.indexOf(term) === -1) return;
      const n = useSubject.get(code) || 0;
      rows.push('<tr><td class="mono">' + code + '</td><td>' + esc(label) +
        (note ? '<span class="qrow__note">' + richText(note) + '</span>' : '') + '</td>' +
        '<td class="qrow__count">' + (n ? '<span class="badge badge--live">' + n + ' בפיד</span>' : '') + '</td></tr>');
    });
    tableBox.innerHTML = rows.length
      ? '<table class="qtable"><thead><tr><th>קוד</th><th>נושא</th><th>בפיד</th></tr></thead><tbody>' +
        rows.join('') + '</tbody></table>'
      : '<p class="empty">אין התאמה. נסו מילה אחרת — או חלק מהקוד.</p>';
  }

  subjSel.addEventListener('change', build);
  condSel.addEventListener('change', build);
  search.addEventListener('input', renderTable);
  build();
  renderTable();
}

/* --- מסך 5: המילון והכרטיסיות ------------------------------------------ */

/*
  שני מצבים לאותו חומר, כי שתי פעולות שונות: **חיפוש** כשנתקלים
  בקיצור ולא מבינים, ו**שינון** כשרוצים שלא להיתקל בו שוב.

  לכל ערך מוצג גם משפט אמיתי מהפיד שבו הקיצור מופיע. הדוגמה נמצאת
  בזמן ריצה ולא נכתבה מראש: כך היא תמיד עדכנית, וכך גם אי אפשר
  לכתוב כאן דוגמה שלא באמת קיימת.
*/
function findUsage(term) {
  const needle = term.toUpperCase();
  for (const n of state.feed) {
    const text = n.text || '';
    const lines = text.split('\n');
    for (const line of lines) {
      const idx = line.toUpperCase().indexOf(needle);
      if (idx === -1) continue;
      const before = line[idx - 1];
      const after = line[idx + needle.length];
      const boundary = (c) => c === undefined || !/[A-Z0-9]/i.test(c);
      if (boundary(before) && boundary(after)) return { line: line.trim(), id: n.id };
    }
  }
  return null;
}

function initGlossary() {
  const listBox = el('gl-list');
  const search = el('gl-search');
  const groupBox = el('gl-groups');
  const countBox = el('gl-count');
  if (!listBox) return;

  /*
    נפתח על "החשובים ביותר" ולא על הכול. הרשימה המלאה היא 143 ערכים
    עם דוגמה לכל אחד — מגילה שאי אפשר לסרוק, ושדוחפת את הכרטיסיות
    אל מחוץ להישג יד. מי שרוצה את כולם לוחץ כפתור אחד.
  */
  let group = 'hot';
  const usageCache = new Map();

  groupBox.innerHTML = '<button type="button" class="chip" data-g="hot" aria-pressed="true">החשובים ביותר</button>' +
    '<button type="button" class="chip" data-g="all" aria-pressed="false">הכול</button>' +
    Object.keys(ABBR_GROUPS).map((g) =>
      '<button type="button" class="chip" data-g="' + g + '" aria-pressed="false">' +
      esc(ABBR_GROUPS[g]) + '</button>').join('');

  function entries() {
    const term = (search.value || '').trim().toLowerCase();
    return Object.keys(ABBR).filter((k) => {
      const e = ABBR[k];
      // חיפוש גובר על הקבוצה: מי שמקליד CLSD מחפש את CLSD, ולא
      // אכפת לו באיזו מגירה הוא יושב.
      if (term) return (k + ' ' + e.he + ' ' + (e.note || '')).toLowerCase().indexOf(term) !== -1;
      if (group === 'hot' && !e.hot) return false;
      if (group !== 'all' && group !== 'hot' && e.g !== group) return false;
      return true;
    }).sort();
  }

  function render() {
    const keys = entries();
    countBox.textContent = keys.length + ' מתוך ' + Object.keys(ABBR).length + ' ערכים';
    if (!keys.length) {
      listBox.innerHTML = '<p class="empty">אין ערך תואם. נסו לחפש את המילה בעברית — המילון מחפש גם בתרגום.</p>';
      return;
    }
    listBox.innerHTML = keys.map((k) => {
      const e = ABBR[k];
      if (!usageCache.has(k)) usageCache.set(k, findUsage(k));
      const use = usageCache.get(k);
      return '<li class="gl-item' + (e.hot ? ' gl-item--hot' : '') + '">' +
        '<div class="gl-item__head"><span class="gl-item__term mono">' + esc(k) + '</span>' +
        '<span class="gl-item__he">' + esc(e.he) + '</span>' +
        (e.hot ? '<span class="badge badge--hot">שכיח</span>' : '') + '</div>' +
        (e.note ? '<p class="gl-item__note">' + richText(e.note) + '</p>' : '') +
        (use ? '<p class="gl-item__use"><span class="gl-item__use-tag">מהפיד</span> <span class="mono">' +
          esc(use.line) + '</span> <span class="muted">(' + esc(use.id) + ')</span></p>' : '') +
        '</li>';
    }).join('');
  }

  groupBox.addEventListener('click', (ev) => {
    const btn = ev.target.closest('.chip');
    if (!btn) return;
    group = btn.dataset.g;
    groupBox.querySelectorAll('.chip').forEach((c) => c.setAttribute('aria-pressed', String(c === btn)));
    render();
  });
  search.addEventListener('input', render);
  render();

  initFlashcards();
}

/*
  כרטיסיות. חפיסה קטנה בכוונה — עשרה ערכים בסבב — כי חפיסה בת מאה
  נזנחת אחרי שתיים־עשרה. מה שלא ידעתם חוזר לסוף החפיסה, ולא נעלם.
*/
function initFlashcards() {
  const card = el('fc-card');
  if (!card) return;
  const front = el('fc-front');
  const back = el('fc-back');
  const progress = el('fc-progress');
  const scoreBox = el('fc-score');

  let deck = [];
  let idx = 0;
  let known = 0;
  let flipped = false;

  function build() {
    const pool = Object.keys(ABBR).filter((k) => ABBR[k].hot);
    const extra = Object.keys(ABBR).filter((k) => !ABBR[k].hot);
    // מערבבים, ומעדיפים את השכיחים — הם מה שבאמת חוזר בכל הודעה.
    deck = shuffle(pool).concat(shuffle(extra)).slice(0, 12);
    idx = 0; known = 0;
    show();
  }

  function show() {
    if (idx >= deck.length) {
      front.innerHTML = '<p class="fc-done">סיימתם את החפיסה.</p>';
      back.innerHTML = '';
      progress.textContent = '';
      scoreBox.textContent = 'ידעתם ' + known + ' מתוך ' + deck.length + '.';
      card.classList.remove('fc--flipped');
      return;
    }
    const key = deck[idx];
    const e = ABBR[key];
    front.innerHTML = '<span class="fc-term mono">' + esc(key) + '</span>' +
      '<span class="fc-hint">לחצו כדי לגלות</span>';
    back.innerHTML = '<span class="fc-he">' + esc(e.he) + '</span>' +
      (e.note ? '<span class="fc-note">' + esc(e.note) + '</span>' : '');
    progress.textContent = (idx + 1) + ' מתוך ' + deck.length;
    scoreBox.textContent = '';
    flipped = false;
    card.classList.remove('fc--flipped');
  }

  card.addEventListener('click', () => {
    if (idx >= deck.length) return;
    flipped = !flipped;
    card.classList.toggle('fc--flipped', flipped);
  });
  el('fc-known').addEventListener('click', () => { if (idx < deck.length) { known++; idx++; show(); } });
  el('fc-unknown').addEventListener('click', () => {
    if (idx >= deck.length) return;
    // חוזר לסוף החפיסה: מה שלא ידעתם תפגשו שוב לפני הסיום.
    deck.push(deck[idx]);
    idx++;
    show();
  });
  el('fc-restart').addEventListener('click', build);
  build();
}

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/* --- מסך 6: ממיר הזמנים ------------------------------------------------- */

/*
  הטעות שחוזרת יותר מכל אחרת. הנוטאם כתוב UTC, השעון ביד כתוב מקומי,
  והפער הוא שלוש שעות בקיץ ושעתיים בחורף — כלומר גם הפער עצמו משתנה.
  הממיר עובד על **התאריך שנבחר** ולא על היום, כי ב-27 באוקטובר
  התשובה שונה מזו של ה-26.
*/
function initConverter() {
  const dateIn = el('cv-date');
  const timeIn = el('cv-time');
  const out = el('cv-out');
  if (!dateIn) return;

  function run() {
    if (!dateIn.value || !timeIn.value) {
      out.innerHTML = '<p class="muted">בחרו תאריך ושעה.</p>';
      return;
    }
    const [y, mo, d] = dateIn.value.split('-').map(Number);
    const [h, mi] = timeIn.value.split(':').map(Number);
    const utc = new Date(Date.UTC(y, mo - 1, d, h, mi));
    const offset = tzOffsetHours(utc);
    out.innerHTML =
      '<p class="cv-line"><span class="cv-line__tag">בנוטאם (UTC)</span> <span class="mono">' +
      String(y).slice(2) + String(mo).padStart(2, '0') + String(d).padStart(2, '0') +
      String(h).padStart(2, '0') + String(mi).padStart(2, '0') + '</span></p>' +
      '<p class="cv-line cv-line--big"><span class="cv-line__tag">בשעון שלכם</span> <strong>' +
      fmtLocal(utc.toISOString()) + '</strong></p>' +
      '<p class="muted">הפרש: ' + offset + ' שעות. ' +
      (offset === 3 ? 'שעון קיץ.' : offset === 2 ? 'שעון חורף.' : '') + '</p>';
  }

  const now = new Date();
  dateIn.value = now.toISOString().slice(0, 10);
  timeIn.value = now.toISOString().slice(11, 16);
  dateIn.addEventListener('input', run);
  timeIn.addEventListener('input', run);
  el('cv-now').addEventListener('click', () => {
    const n = new Date();
    dateIn.value = n.toISOString().slice(0, 10);
    timeIn.value = n.toISOString().slice(11, 16);
    run();
  });
  run();
}

/* --- מסך 7: התרגול ------------------------------------------------------ */

/*
  שאלות שנבנות מהפיד עצמו. היתרון אינו רק שהן טריות: הן **אינן
  ניתנות לשינון**. אין כאן מאגר של עשרים שאלות שאפשר לזכור את
  תשובותיהן, אלא הודעות אמיתיות מהיום, וכל סבב שונה מקודמו.

  מסיחים נבנים מערכים אמיתיים של הודעות אחרות, לא ממספרים אקראיים.
  מסיח אקראי מסגיר את עצמו ומלמד לנחש; מסיח שנלקח מהודעה שכנה מחייב
  באמת לקרוא.

  לצדן כמה שאלות מושגיות כתובות ביד — הדברים שאי אפשר לגזור מהודעה
  אחת, כמו מה קורה כשאין נוטאם בכלל.
*/

const CONCEPT_QUESTIONS = [
  {
    q: 'שורת Q מסתיימת ב-<span class="mono">3155N03518E010</span>. מה אומר המספר 010?',
    options: ['רדיוס 10 מיילים ימיים סביב הנקודה', 'גובה 1,000 רגל', 'ההודעה בתוקף 10 ימים', 'מספר סידורי של האזור'],
    correct: 0,
    why: 'שלוש הספרות האחרונות בשדה המיקום הן רדיוס במיילים ימיים. הן מגדירות מעטפת עגולה — לא בהכרח את צורת המגבלה עצמה.',
  },
  {
    q: 'בשורת Q כתוב <span class="mono">000/999</span>. מה זה אומר?',
    options: ['ללא הגבלת גובה — מהקרקע עד הסוף', 'מגובה 0 עד 99,900 רגל', 'הגובה לא פורסם', 'ההודעה תקפה 999 שעות'],
    correct: 0,
    why: '000/999 הוא ערך מוסכם שפירושו "כל הגבהים". הוא אינו טווח מדוד, ואין להסיק ממנו שהמגבלה מסתיימת ב-99,900 רגל.',
  },
  {
    q: 'פריט C) הוא <span class="mono">2609011000EST</span>. מה מוסיפה האות EST?',
    options: [
      'זמן הסיום הוא הערכה בלבד ועשוי להשתנות',
      'ההודעה חלה בשעון מזרח ארה"ב',
      'ההודעה כבר הסתיימה',
      'הזמן הוא מקומי ולא UTC',
    ],
    correct: 0,
    why: 'EST הוא Estimated. הסיום מוערך, ואין הודעה נוספת אם הוא משתנה — לכן אין להסתמך עליו כעל שעה מדויקת.',
  },
  {
    q: 'ההודעה אומרת <span class="mono">FM GND UP TO 600M AGL</span>, ובהמשך <span class="mono">CLSD FM GND UP TO 3,700FT AMSL</span>. למה שני מספרים שונים?',
    options: [
      'הראשון הוא גובה הפעילות מעל הקרקע, השני הוא גובה הסגירה מעל פני הים',
      'זו טעות בהודעה',
      'הראשון חל על רחפנים והשני על מטוסים',
      'הראשון בשעות היום והשני בלילה',
    ],
    correct: 0,
    why: 'AGL נמדד מהקרקע שמתחת, AMSL מפני הים. באזור שהקרקע בו מוגבהת, 600 מטר מעל הקרקע יכולים להיות 3,700 רגל מעל פני הים.',
  },
  {
    q: 'לא מצאתם נוטאם על אזור מסוים. מה מותר להסיק?',
    options: [
      'שום דבר — היעדר נוטאם אינו ראיה להיעדר מגבלה',
      'שהאזור פתוח לטיסה',
      'שהמגבלה הקודמת בוטלה',
      'שהאזור אינו במרחב הישראלי',
    ],
    correct: 0,
    why: 'לא כל מגבלה מתפרסמת כנוטאם: יש תיאומים מקומיים, פעילות צבאית והסדרים זמניים שאינם עוברים בערוץ הזה כלל. זו גם האזהרה שבראש המפה.',
  },
  {
    q: 'מה ההבדל בין <span class="mono">NOTAMR</span> ל-<span class="mono">NOTAMC</span>?',
    options: [
      'R מחליפה הודעה קודמת, C מבטלת אותה בלי תחליף',
      'R היא מגבלה, C היא אזהרה',
      'R היא זמנית, C היא קבועה',
      'אין הבדל, שתיהן הודעות חדשות',
    ],
    correct: 0,
    why: 'R = Replace: ההודעה החדשה באה במקום הישנה. C = Cancel: ההודעה הישנה מבוטלת ואין מגבלה חדשה תחתיה.',
  },
  {
    q: 'פריט D) אומר <span class="mono">DAILY 0330-1400 1700-0200</span>. מה קורה בשעה 15:00 UTC?',
    options: [
      'ההודעה אינה פעילה — 15:00 נופל בין שני החלונות',
      'ההודעה פעילה, כי היא בתוך התאריכים של B ו-C',
      'ההודעה פעילה עד 17:00 בכל מקרה',
      'לא ניתן לדעת בלי פריט E',
    ],
    correct: 0,
    why: 'פריט D) מצמצם את החלון של B–C לשעות שנקובות בו בלבד. בין 14:00 ל-17:00 אין חלון, ולכן ההודעה אינה פעילה שם. שימו לב שהחלון השני חוצה חצות.',
  },
  {
    q: 'מה אומר הצירוף <span class="mono">CTN ADZ</span> שחותם הודעות רבות?',
    options: [
      'מומלצת זהירות',
      'האזור סגור לחלוטין',
      'נדרש אישור מהמגדל',
      'ההודעה בוטלה',
    ],
    correct: 0,
    why: 'Caution Advised. הוא נאמר דווקא כשהאזור אינו סגור — יש בו משהו שדורש תשומת לב, ולכן דווקא אותו נוטים לפספס.',
  },
  {
    q: 'פריט F) אומר <span class="mono">GND</span> ופריט G) אומר <span class="mono">3700FT AMSL</span>, בעוד שורת Q אומרת <span class="mono">000/037</span>. מי גובר?',
    options: [
      'פריטי F ו-G — הם הניסוח המפורש',
      'שורת Q — היא הרשמית',
      'הנמוך מבין השניים',
      'אין הבדל, שניהם זהים תמיד',
    ],
    correct: 0,
    why: 'שורת Q מעגלת כלפי מעלה לרמות טיסה שלמות ונועדה לסינון ממוכן. כשיש ניסוח מפורש בפריטי F/G — הוא המדויק, והוא הקובע.',
  },
  {
    q: 'מהי הודעת <span class="mono">TRIGGER NOTAM</span>?',
    options: [
      'הודעה שמבשרת שעדכון לפמ"ת נכנס לתוקף — אינה מגבלה בשטח',
      'הודעה על ירי או פעילות חימוש',
      'הודעה שמופעלת אוטומטית בשעת חירום',
      'הודעה שמבטלת את כל הקודמות',
    ],
    correct: 0,
    why: 'תפקידה היחיד להצביע על שינוי בספר עצמו, כדי שמי שקורא רק נוטאמים יידע שהפמ"ת השתנה. אין מאחוריה סגירה או אזור.',
  },
];

/** בונה שאלה מהודעה אמיתית. מחזיר null אם ההודעה אינה מתאימה לסוג. */
const QUIZ_BUILDERS = [
  // מה הנושא
  function subjectQ(n, pool) {
    if (!n.q || !n.q.subject) return null;
    const others = uniqueValues(pool, (x) => (x.q && x.q.subject) || null, n.q.subject, 3);
    if (others.length < 3) return null;
    return {
      q: 'לפי שורת ה-Q, על מה ההודעה הזאת?',
      raw: n.raw,
      options: [n.q.subject].concat(others),
      correctValue: n.q.subject,
      why: 'הקוד הוא ' + n.q.q_code + ': שתי האותיות הראשונות אחרי Q הן הנושא (' +
        n.q.subject_code + ' = ' + n.q.subject + '), ושתי האחרונות הן המצב.',
    };
  },
  // עד איזה גובה
  function ceilingQ(n, pool) {
    const up = n.upper_limit && n.upper_limit.feet;
    if (!up) return null;
    const others = uniqueValues(pool, (x) => (x.upper_limit && x.upper_limit.feet) || null, up, 3)
      .map((v) => fmtFeet(v));
    if (others.length < 3) return null;
    return {
      q: 'עד איזה גובה חלה ההודעה?',
      raw: n.raw,
      options: [fmtFeet(up)].concat(others),
      correctValue: fmtFeet(up),
      why: 'פריט G) נושא את הגבול העליון המפורש: ' + (n.upper_limit.raw || '') + '.',
    };
  },
  // מתי מסתיים
  function endQ(n) {
    if (!n.valid_to || !n.valid_to.iso) return null;
    const end = new Date(n.valid_to.iso);
    const correct = fmtLocalShort(n.valid_to.iso);
    const distract = [
      // ההפרש בין UTC למקומי — הטעות הנפוצה ביותר, ולכן המסיח הנכון.
      fmtLocalShort(new Date(end.getTime() - tzOffsetHours(end) * 3600000).toISOString()),
      fmtLocalShort(new Date(end.getTime() + 86400000).toISOString()),
      fmtLocalShort(new Date(n.valid_from && n.valid_from.iso ? n.valid_from.iso : end.getTime() - 7200000)),
    ].filter((v, i, arr) => v !== correct && arr.indexOf(v) === i);
    if (distract.length < 3) return null;
    return {
      q: 'מתי פג תוקף ההודעה, בשעון ישראל?',
      raw: n.raw,
      options: [correct].concat(distract.slice(0, 3)),
      correctValue: correct,
      why: 'פריט C) הוא ' + n.valid_to.raw + ' — כלומר ' + fmtUtc(n.valid_to.iso) +
        ', ובשעון ישראל ' + fmtLocal(n.valid_to.iso) + '.',
    };
  },
  // היכן
  function scopeQ(n) {
    if (!n.q || !n.q.scope || !Q_SCOPE[n.q.scope_code]) return null;
    const others = Object.keys(Q_SCOPE)
      .filter((k) => k !== n.q.scope_code)
      .map((k) => Q_SCOPE[k])
      .filter((v) => v !== n.q.scope);
    if (others.length < 3) return null;
    return {
      q: 'מה היקף ההודעה, לפי שדה 5 בשורת Q?',
      raw: n.raw,
      options: [n.q.scope].concat(shuffle(others).slice(0, 3)),
      correctValue: n.q.scope,
      why: 'שדה 5 הוא ' + n.q.scope_code + ' = ' + n.q.scope + '. הוא אומר לאיזה חלק בתדריך ההודעה שייכת.',
    };
  },
];

function uniqueValues(pool, pick, exclude, count) {
  const seen = new Set();
  const out = [];
  shuffle(pool).forEach((item) => {
    const v = pick(item);
    if (v === null || v === undefined || v === exclude || seen.has(v)) return;
    seen.add(v);
    if (out.length < count) out.push(v);
  });
  return out;
}

function buildQuiz(count) {
  const pool = state.feed.filter((n) => n.q && !n.administrative);
  const questions = [];
  if (pool.length > 8) {
    const picks = shuffle(pool).slice(0, 40);
    picks.forEach((n) => {
      if (questions.length >= count - 3) return;
      const builder = QUIZ_BUILDERS[Math.floor(Math.random() * QUIZ_BUILDERS.length)];
      const q = builder(n, pool);
      if (q) questions.push(q);
    });
  }
  // תמיד לפחות שלוש מושגיות: הן מכסות את מה שהודעה בודדת לא מלמדת.
  shuffle(CONCEPT_QUESTIONS).slice(0, Math.max(3, count - questions.length)).forEach((q) => {
    questions.push(Object.assign({}, q, { correctValue: q.options[q.correct] }));
  });
  return shuffle(questions).slice(0, count).map((q) => {
    const options = shuffle(q.options);
    return Object.assign({}, q, { options, correct: options.indexOf(q.correctValue) });
  });
}

function initQuiz() {
  const box = el('quiz-box');
  if (!box) return;
  const bar = el('quiz-progress');
  const scoreBox = el('quiz-score');

  let questions = [];
  let idx = 0;
  let score = 0;
  let answered = false;

  function start() {
    questions = buildQuiz(10);
    idx = 0; score = 0;
    render();
  }

  function render() {
    answered = false;
    if (idx >= questions.length) {
      const pct = Math.round((score / questions.length) * 100);
      box.innerHTML = '<div class="quiz-done"><p class="quiz-done__score">' + score + ' מתוך ' +
        questions.length + '</p><p class="quiz-done__note">' + esc(verdict(pct)) + '</p></div>';
      bar.style.width = '100%';
      scoreBox.textContent = '';
      return;
    }
    const q = questions[idx];
    bar.style.width = Math.round((idx / questions.length) * 100) + '%';
    scoreBox.textContent = 'שאלה ' + (idx + 1) + ' מתוך ' + questions.length + ' · ' + score + ' נכונות';
    let html = '<p class="quiz-q">' + q.q + '</p>';
    if (q.raw) {
      html += '<pre class="quiz-raw">' + esc(q.raw) + '</pre>';
    }
    html += '<ol class="quiz-options">' + q.options.map((opt, i) =>
      '<li><button type="button" class="quiz-opt" data-i="' + i + '">' + esc(opt) + '</button></li>').join('') +
      '</ol><div class="quiz-feedback" id="quiz-feedback"></div>';
    box.innerHTML = html;
  }

  function verdict(pct) {
    if (pct === 100) return 'מושלם. אתם קוראים נוטאם.';
    if (pct >= 80) return 'טוב מאוד. מה שנשאר הוא הפרטים הקטנים — והם בדיוק אלה שעולים ביוקר.';
    if (pct >= 50) return 'השלד ברור, הפרטים עוד לא. שווה סבב נוסף במפרק ובמלכודות.';
    return 'זה בסדר גמור להתחיל כאן. חזרו למסך "השיטה" — חמש השאלות הן כל מה שצריך בהתחלה.';
  }

  box.addEventListener('click', (ev) => {
    const btn = ev.target.closest('.quiz-opt');
    if (!btn || answered) return;
    answered = true;
    const q = questions[idx];
    const chosen = +btn.dataset.i;
    const ok = chosen === q.correct;
    if (ok) score++;
    box.querySelectorAll('.quiz-opt').forEach((b, i) => {
      b.disabled = true;
      if (i === q.correct) b.classList.add('quiz-opt--right');
      else if (i === chosen) b.classList.add('quiz-opt--wrong');
    });
    el('quiz-feedback').innerHTML =
      '<p class="quiz-verdict ' + (ok ? 'is-right' : 'is-wrong') + '">' +
      (ok ? 'נכון.' : 'לא. התשובה: ' + esc(q.options[q.correct])) + '</p>' +
      '<p class="quiz-why">' + richText(q.why) + '</p>' +
      '<button type="button" class="btn btn--primary" id="quiz-next">' +
      (idx + 1 >= questions.length ? 'לסיכום' : 'לשאלה הבאה') + '</button>';
    el('quiz-next').addEventListener('click', () => { idx++; render(); });
    el('quiz-next').focus();
  });

  el('quiz-restart').addEventListener('click', start);
  start();
}

/* --- חלונית הקיצור ------------------------------------------------------ */

/*
  כל קיצור מוכר בכל טקסט בעמוד הוא כפתור, ולחיצה עליו פותחת שורה
  אחת: מה זה. זו הפעולה שהכי הרבה פעמים תידרש כאן, ולכן היא צריכה
  להיות זולה — בלי לעזוב את ההודעה שקוראים, בלי לחפש במילון.
*/
function initAbbrPopover() {
  const pop = document.createElement('div');
  pop.className = 'abbr-pop';
  pop.hidden = true;
  pop.setAttribute('role', 'dialog');
  document.body.appendChild(pop);

  function close() { pop.hidden = true; }

  document.addEventListener('click', (ev) => {
    const btn = ev.target.closest('.abbr');
    if (!btn) {
      if (!ev.target.closest('.abbr-pop')) close();
      return;
    }
    const key = btn.dataset.abbr;
    const e = ABBR[key];
    if (!e) return;
    pop.innerHTML = '<button type="button" class="abbr-pop__x" aria-label="סגירה">✕</button>' +
      '<p class="abbr-pop__term mono">' + esc(key) + '</p>' +
      '<p class="abbr-pop__he">' + esc(e.he) + '</p>' +
      (e.note ? '<p class="abbr-pop__note">' + richText(e.note) + '</p>' : '');
    pop.hidden = false;
    const r = btn.getBoundingClientRect();
    const top = r.bottom + window.scrollY + 6;
    // ההצמדה נעשית אחרי ההצגה, כי לפניה לרוחב החלונית אין ערך.
    const width = pop.offsetWidth;
    let left = r.left + window.scrollX + r.width / 2 - width / 2;
    left = Math.max(8, Math.min(left, document.documentElement.clientWidth - width - 8));
    pop.style.top = top + 'px';
    pop.style.left = left + 'px';
  });

  document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') close(); });
  window.addEventListener('resize', close);
}

/* --- הרכבה --------------------------------------------------------------- */

async function main() {
  initTabs();
  initAbbrPopover();
  initConverter();

  // הפיד נטען פעם אחת ומשרת את כל המסכים שנשענים על נתונים אמיתיים.
  await Promise.all([loadFeed(), loadFieldNames()]);

  const note = el('feed-note');
  if (note) {
    if (state.feedOk) {
      note.innerHTML = 'הדוגמאות החיות בעמוד נלקחות מ־<strong>' + state.feed.length +
        '</strong> הנוטאמים שהיו פעילים בעדכון האחרון' +
        (state.generatedAt ? ' (' + esc(fmtLocal(state.generatedAt)) + ')' : '') + '.';
    } else {
      note.innerHTML = 'הפיד החי לא נטען, והעמוד עובד על הדוגמאות המוטבעות בלבד. ' +
        'אם פתחתם את הקובץ ישירות מהדיסק — הריצו שרת מקומי, כפי שכתוב ב-README.';
      note.classList.add('feed-note--off');
    }
  }

  initDissector();
  initDecoder();
  initQCodes();
  initGlossary();
  initQuiz();
}

document.addEventListener('DOMContentLoaded', main);

/* ---------------------------------------------------------------------------
   מגבלות מרחב אווירי — ישראל
   הדף קורא שני קבצים סטטיים מתוך המאגר. אין קריאה למקור חיצוני בזמן טעינה
   (מקורות הנוטאמים חוסמים CORS), ואין שום לוגיקת סינון — רק סימון ויזואלי.
--------------------------------------------------------------------------- */
'use strict';

const CENTER = [31.9558, 35.3392];   // כוכב השחר
const ZOOM = 11;
// גבולות הכיסוי הארצי, לכפתור "כל הארץ".
const COUNTRY_BOUNDS = [[29.4, 34.2], [33.4, 35.9]];
const TZ = 'Asia/Jerusalem';
const NM_TO_M = 1852;
const STALE_AFTER_MS = 3 * 60 * 60 * 1000;   // ה-cron רץ כל שעה; שלוש שעות = תקלה

const ZONE_STYLES = {
  prohibited: { color: '#b3151b', label: 'אסור לטיסה' },
  restricted: { color: '#c2410c', label: 'מוגבל לטיסה' },
  danger:     { color: '#a16207', label: 'מסוכן לטיסה' },
  uav:        { color: '#6b21a8', label: 'אסור לכטב"ם' },
  // מכשול קבוע — בלון מעוגן. שחור, כי כבל בגובה 3,400 רגל אינו
  // "אזור מוגבל" אלא דבר פיזי שמתנגשים בו.
  obstacle:   { color: '#111827', label: 'מכשול קבוע' },
  other:      { color: '#334155', label: 'מגבלה קבועה' }
};

const NOTAM_LOW = '#d1006e';
const NOTAM_HIGH = '#0f6fa8';
const LOW_ALTITUDE_FT = 3000;
// מזג אוויר בגוון שלישי, שאינו אדום ואינו כחול — כדי שלא ייקרא כמגבלה.
const WEATHER_COLOR = '#0f766e';
// שמורות טבע — ירוק, ובכוונה החלש מכולם. השכבה הזאת היא רקע להתמצאות
// ולא מגבלה, ואסור לה להתחרות ויזואלית באזורים שכן אוסרים טיסה.
const RATAG_COLOR = '#15803d';
// נתיבי CVFR — סגול. הרשת הזאת אינה מגבלה אלא **היכן מותר לטוס**,
// והיא צריכה גוון משלה שלא ייקרא לא כאיסור (אדום), לא כנוטאם (כחול)
// ולא כרקע (ירוק). קו דק, כי נתיב הוא ציר ולא שטח.
const CVFR_COLOR = '#7c3aed';

/**
 * מעל כמה מייל ימי עיגול של שורת Q נחשב **מעטפת** ולא אזור.
 *
 * שדה 8 בשורת Q אינו צורת ההגבלה. ICAO מגדיר אותו כעיגול שמקיף את
 * אזור ההשפעה, מעוגל כלפי מעלה — כלומר תיבה חוסמת לצורכי חיפוש
 * וסינון, לא גיאומטריה. הטקסט עצמו מוכיח את זה:
 *
 *   C1579/26 — עיגול 87 מייל (רדיוס ~160 ק"מ), והטקסט אומר
 *   "FM JORDAN BOUNDARY TO **6KM**". רצועה של 6 ק"מ.
 *
 *   C1742/26 — עיגול 54 מייל, והטקסט הוא **רשימת נתיבים**:
 *   "CVFR RTE CLSD YAHEL-BMNUH-ZOFAR…". קווים, לא דיסקה.
 *
 * מעטפת כזאת אינה מצוירת כלל. גם קו בלבד עדיין מצייר צורה שאינה
 * קיימת, ומעמיס על המפה בלי להוסיף מידע: מרכז המעטפת אינו מרכז
 * ההגבלה, והרדיוס אינו מרחקה. מה שכן קיים — הזהות, הזמנים, הגבהים
 * והנוסח המלא — נמצא ברשימה, והיא מלאה תמיד.
 *
 * זה **אינו** ויתור על הנתון: כשהנוטאם מפרט קודקודים בגוף ההודעה,
 * `extract_area` מוציא אותם והאזור מצויר במלואו. הכלל הזה חל רק על
 * מי שאין לו שום גבול מפורש.
 *
 * הסף עצמו הוא החלטת תצוגה ולא נתון מהמקור, ולכן הוא כתוב כאן במפורש.
 */
const ENVELOPE_NM = 20;

/**
 * תוויות הסיווג המשני של הפמ"ת. המפתחות נקבעים ב-scripts/aip_classify.py,
 * וכאן רק השמות והסדר שבו הם מוצגים.
 *
 * הנושא נגזר ממילים שכתובות **בשם הרשמי של האזור** — "שטח אש 209"
 * נושא את המילים "שטח אש". זו קריאה של הכתוב ולא ניחוש לפי היכרות
 * עם המקום. אזור בלי מילת מפתח נופל ל-`other`.
 *
 * מה שאין: סוג המתקן. שתי הטבלאות בפמ"ת מוסרות קואורדינטות, גבהים,
 * שם וקוד — ואין בהן עמודת ייעוד. לכן אי אפשר להפריד בית כלא ממתקן
 * משטרה בלי לנחש, ולא ננחש.
 */
const AIP_FLOORS = {
  ground:  { label: 'מהקרקע' },
  low:     { label: 'עד 4,000 רגל' },
  high:    { label: 'מעל 4,000 רגל' },
  unknown: { label: 'ללא רצפה מוגדרת' }
};

const AIP_THEMES = {
  firing:   { label: 'שטחי אש ומטווחים' },
  judea:    { label: 'יהודה ושומרון' },
  offshore: { label: 'אסדות ומתקנים ימיים' },
  balloon:  { label: 'בלונים' },
  drop:     { label: 'גלילי הצנחה' },
  model:    { label: 'אתרי רחפנים וטיסנים' },
  police:   { label: 'מתקני משטרה' },
  transit:  { label: 'מרחבים ומעברים' },
  other:    { label: 'ללא מילת סיווג בשם' }
};

/**
 * "לא צוין" נשמע כאילו לנוטאם אין תוקף מוגדר, וזה לא נכון: יש לו תוקף,
 * הוא פשוט עוד לא נמשך. זמני התוקף נפתחים בכפתור ה-`+` באתר של רש"ת,
 * וזו בקשה נפרדת לכל הודעה — המשיכה עושה אותן בקצב מרוסן ושומרת
 * מטמון, אז הודעה חדשה מופיעה תחילה בלי זמנים.
 */
const NO_VALIDITY = 'טרם נמשך';

const el = (id) => document.getElementById(id);

/**
 * מונה שכבה. נשמר גם כשהאלמנט עדיין לא קיים.
 *
 * לוח הבקרה נבנה מהנתונים — הוא צריך את הספירות של תת־השכבות — ולכן
 * הוא נוצר **אחרי** שהשכבות צוירו. הכתיבה למונה קורית לפני כן, וללא
 * החיץ הזה היא הייתה נופלת על אלמנט שאינו קיים.
 */
const layerCounts = new Map();

function setCount(id, value) {
  layerCounts.set(id, value);
  const node = el('count-' + id);
  if (node) node.textContent = value;
}

function flushCounts() {
  layerCounts.forEach((value, id) => {
    const node = el('count-' + id);
    if (node) node.textContent = value;
  });
}

/* --- עזרי טקסט -------------------------------------------------------- */

function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const dateFmt = new Intl.DateTimeFormat('he-IL', {
  dateStyle: 'short', timeStyle: 'short', timeZone: TZ
});

function fmtTime(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d) ? null : dateFmt.format(d);
}

/** מציג את פריט הזמן של הנוטאם, כולל המקרים שאינם תאריך: PERM, EST, מיידי. */
function fmtStamp(stamp, fallback) {
  if (!stamp) return fallback;
  if (stamp.permanent) return 'קבוע';
  const formatted = fmtTime(stamp.iso);
  if (!formatted) return stamp.raw || fallback;
  return stamp.estimated ? formatted + ' (משוער)' : formatted;
}

const relFmt = new Intl.RelativeTimeFormat('he', { numeric: 'auto' });

function relativeAge(ms) {
  const mins = Math.round(ms / 60000);
  if (Math.abs(mins) < 60) return relFmt.format(-mins, 'minute');
  const hours = Math.round(mins / 60);
  if (Math.abs(hours) < 24) return relFmt.format(-hours, 'hour');
  return relFmt.format(-Math.round(hours / 24), 'day');
}

/** טווח הגבהים בשפה אנושית. F)/G) מדויקים יותר משורת Q, אז הם קודמים. */
function altitudeText(n) {
  const lower = n.lower_limit && n.lower_limit.raw;
  const upper = n.upper_limit && n.upper_limit.raw;
  if (lower || upper) return `${lower || '—'} עד ${upper || '—'}`;
  const alt = n.altitude;
  // אותה סיבה כמו בזמני התוקף: פריטי F)/G) נפתחים רק בכפתור ההרחבה
  // באתר, ולא מגיעים לרשימה.
  if (!alt) return NO_VALIDITY;
  if (alt.unlimited) return 'ללא הגבלת גובה';
  return `${alt.lower_ft.toLocaleString('he-IL')} עד ${alt.upper_ft.toLocaleString('he-IL')} רגל`;
}

function subjectText(n) {
  if (!n.q) return null;
  const parts = [n.q.subject, n.q.condition].filter(Boolean);
  return parts.length ? parts.join(' — ') : n.q.q_code;
}

/* --- מפה -------------------------------------------------------------- */

let map = null;
let aipLayer = null;
let notamLayer = null;
let weatherLayer = null;

/**
 * תת־שכבות לפי קטגוריה.
 *
 * 137 אזורי פמ"ת ו-127 נוטאמים על מפה אחת זה קיר. החלוקה נותנת לעין
 * דרך להיכנס פנימה: לכבות את הכטב"ם ולראות רק את האסור, או לבודד את
 * שדות התעופה.
 *
 * **הרשימה שמתחת למפה אינה מסוננת לעולם.** זו הבחנה מהותית ולא
 * טכנית: המתגים כאן שולטים במה שמצויר, לא במה שקיים. נוטאם שכובה
 * בשכבה עדיין מופיע ברשימה במלואו, וכל המתגים דולקים כברירת מחדל.
 */
const sublayers = new Map();   // מפתח קטגוריה -> {group, count, on}

/**
 * מרשם הצורות, לסינון לפי **שני צירים בו־זמנית**.
 *
 * תת־שכבה אחת לכל קטגוריה מספיקה כל עוד יש ציר סינון אחד. ברגע
 * שרוצים גם "לפי נושא" וגם "לפי מצב תוקף", צורה צריכה להיות שייכת
 * לשתי קבוצות — ו-Leaflet לא יודע כזה. לכן כל צורה נרשמת כאן עם
 * התכונות שלה, וההצגה נגזרת מהצטלבות של כל הצירים הפעילים.
 */
const registry = [];
const filters = new Map();     // ציר -> Set של ערכים כבויים
const notamShapes = new Map();   // מזהה נוטאם -> שכבה, לכפתור "הצג במפה"

/**
 * מאתחל את המפה. מחזיר false אם Leaflet לא נטען — במקרה כזה הדף ממשיך
 * לעבוד בלי מפה. הרשימה וחותמת הזמן הן המידע הקריטי, והן לא צריכות אותה.
 */
function initMap() {
  if (typeof L === 'undefined') return false;

  map = L.map('map', { center: CENTER, zoom: ZOOM, zoomControl: true });

  const tiles = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
  }).addTo(map);

  // רקע המפה מגיע משרת אריחים חיצוני. אם הוא לא נטען, האזורים עדיין
  // מצוירים במיקומם הנכון — אבל צריך להגיד את זה, לא להשאיר מסך ריק.
  let warned = false;
  tiles.on('tileerror', () => {
    if (warned) return;
    warned = true;
    addAlert('<strong>רקע המפה לא נטען.</strong> האזורים והעיגולים מצוירים במיקומם הנכון, אבל בלי מפת הרקע. בדקו את החיבור לרשת.', 'warn');
  });

  // פאנלים נפרדים כדי שעיגולי הנוטאם יהיו תמיד מעל פוליגוני הפמ"ת.
  map.createPane('ratag').style.zIndex = 400;     // הכי מתחת — רקע להתמצאות
  // רשת ה-CVFR היא פוליגון אחד בגודל המדינה. היא יושבת נמוך בכוונה:
  // מעליה היא הייתה בולעת כל לחיצה על אזור פמ"ת או נוטאם שבתוכה,
  // וממילא היא מציינת **היכן מותר**, כלומר רקע למגבלות ולא מגבלה.
  map.createPane('cvfr').style.zIndex = 402;
  map.createPane('weather').style.zIndex = 405;   // מתחת למגבלות — הן החשובות
  map.createPane('aip').style.zIndex = 410;
  map.createPane('notam').style.zIndex = 420;

  aipLayer = L.layerGroup().addTo(map);
  notamLayer = L.layerGroup().addTo(map);
  // לא נוסף למפה כאן: שכבת מזג האוויר כבויה עד שהמתג נדלק.
  weatherLayer = L.layerGroup();

  // הכלי התחיל כמפה של מטה בנימין והפך לארצי. כפתור "בית" שמצביע
  // על אזור אחד כבר אינו מייצג את מה שהדף מראה, ולכן נשאר כפתור
  // אחד: החזרה לתצוגה הארצית אחרי שהתקרבו למקום מסוים.
  const views = L.control({ position: 'topright' });
  views.onAdd = () => {
    const box = L.DomUtil.create('div', 'view-switch');
    box.innerHTML = '<button type="button" data-view="country">כל הארץ</button>';
    L.DomEvent.disableClickPropagation(box);
    box.addEventListener('click', (e) => {
      const view = e.target.getAttribute('data-view');
      if (view === 'country') {
        // מתאימים לגבולות השכבה עצמה כשהיא קיימת — היא צרה וגבוהה,
        // ותיבה קבועה משאירה שוליים מיותרים.
        //
        // `aipLayer` מכיל קבוצות־משנה לפי קטגוריה, לא צורות. ל-LayerGroup
        // אין `getBounds` ואין `getLatLng`, ולכן `featureGroup` עליו נופל.
        // צריך לשטח שכבה אחת פנימה.
        const shapes = aipLayer.getLayers()
          .flatMap((layer) => (layer.getLayers ? layer.getLayers() : [layer]));
        const bounds = shapes.length
          ? L.featureGroup(shapes).getBounds()
          : L.latLngBounds(COUNTRY_BOUNDS);
        map.fitBounds(bounds, { padding: [20, 20] });
      }
    });
    return box;
  };
  views.addTo(map);
  return true;
}

/* --- שכבת הפמ"ת ------------------------------------------------------- */

function zoneKind(props) {
  const raw = String(props.type || props.kind || props.category || '').toLowerCase();
  const hebrew = String(props.type || '');
  if (raw.includes('uav') || raw.includes('drone') || hebrew.includes('כטב')) return 'uav';
  if (raw.includes('prohib') || hebrew.includes('אסור')) return 'prohibited';
  if (raw.includes('restrict') || hebrew.includes('מוגבל')) return 'restricted';
  if (raw.includes('danger') || hebrew.includes('מסוכן')) return 'danger';
  if (hebrew.includes('מכשול')) return 'obstacle';
  return 'other';
}

/** רושם צורה עם כל התכונות שאפשר לסנן לפיהן, ומוסיף אותה למפה. */
function register(shape, parent, traits) {
  registry.push({ shape, parent, traits });
  parent.addLayer(shape);
  Object.entries(traits).forEach(([axis, value]) => {
    const key = axis + ':' + value;
    const entry = sublayers.get(key) || { count: 0, on: true, axis, value };
    entry.count += 1;
    sublayers.set(key, entry);
  });
  return shape;
}

/**
 * שטח מקורב של צורה, במעלות רבועות. משמש **רק** לסדר הלחיצה.
 *
 * תיבה חוסמת ולא השטח האמיתי — ההבדל לא משנה כאן, כי כל מה שנדרש
 * הוא להשוות "מי גדול ממי". נקודה מקבלת אפס, ולכן היא תמיד העליונה.
 */
function hitArea(shape) {
  if (typeof shape.getBounds !== 'function') return 0;
  let bounds;
  try {
    bounds = shape.getBounds();
  } catch (err) {
    return 0;
  }
  if (!bounds || !bounds.isValid()) return 0;
  return Math.abs(bounds.getNorth() - bounds.getSouth())
       * Math.abs(bounds.getEast() - bounds.getWest());
}

/**
 * מסדר את הצורות כך שהקטנה מביניהן תמיד למעלה.
 *
 * הבעיה: SVG מכריע לחיצה לפי סדר ה-DOM, והסדר עד עכשיו היה סדר
 * הקריאה מהקובץ. נוטאם ענק שנקרא אחרון ישב מעל אזור קטן שבתוכו,
 * ואי אפשר היה ללחוץ על הקטן בכלל.
 *
 * הפתרון: מיון לפי שטח בסדר יורד, ואז `bringToFront` על כל אחד לפי
 * התור. הגדולה נדחפת קדימה ראשונה, הקטנה אחרונה — ולכן הקטנה נשארת
 * למעלה. הכלל נכון בתוך פאנל; בין פאנלים ה-z-index עדיין קובע, וזו
 * הסיבה שהעיגולים הענקיים גם מאבדים מילוי.
 */
function orderByHitPriority() {
  registry
    .filter(({ shape, parent }) => parent.hasLayer(shape))
    .map(({ shape }) => ({ shape, area: hitArea(shape) }))
    .sort((a, b) => b.area - a.area)
    .forEach(({ shape }) => {
      if (typeof shape.bringToFront === 'function') shape.bringToFront();
    });
}

/** צורה מוצגת רק אם **כל** התכונות שלה דלוקות. */
function applyFilters() {
  registry.forEach(({ shape, parent, traits }) => {
    const visible = Object.entries(traits).every(([axis, value]) => {
      const off = filters.get(axis);
      return !off || !off.has(value);
    });
    const shown = parent.hasLayer(shape);
    if (visible && !shown) parent.addLayer(shape);
    if (!visible && shown) parent.removeLayer(shape);
  });
  // הוספה מחדש דוחפת לסוף ה-DOM, ולכן הסדר נבנה שוב אחרי כל סינון.
  orderByHitPriority();
}

function renderAip(geojson) {
  const features = (geojson && geojson.features) || [];
  setCount('aip', features.length);
  if (!features.length || !map) return features.length;

  features.forEach((feature) => {
    const kind = zoneKind(feature.properties || {});
    const color = ZONE_STYLES[kind].color;
    const shape = L.geoJSON(feature, {
      pane: 'aip',
      style: { color, weight: 2.5, opacity: 1, fillColor: color, fillOpacity: 0.18 },
      onEachFeature: (f, layer) => {
        layer.bindPopup(aipPopup(f.properties || {}), { maxWidth: 340 });
      }
    });
    // שלושה צירים חוצים: סוג ההגבלה, רצפת הגובה, ונושא האזור.
    // הסיווג מגיע מהקובץ ולא מחושב כאן — ראו scripts/aip_classify.py.
    const props = feature.properties || {};
    register(shape, aipLayer, {
      aip: kind,
      floor: props.floor_band || 'unknown',
      theme: props.theme || 'other'
    });
  });

  return features.length;
}

function aipPopup(p) {
  const kind = zoneKind(p);
  const rows = [];
  if (p.name) rows.push(['שם', p.name]);
  rows.push(['סוג', p.type || ZONE_STYLES[kind].label]);
  const lower = p.lower_limit || p.lower;
  const upper = p.upper_limit || p.upper;
  if (lower || upper) rows.push(['גבהים', `${lower || '—'} עד ${upper || '—'}`]);
  if (p.authority) rows.push(['גורם מוסמך', p.authority]);
  if (p.source) rows.push(['מקור', p.source]);

  return `
    <div class="card">
      <div class="card__id">${esc(p.id || p.designator || 'אזור')}</div>
      <p class="card__title">${esc(ZONE_STYLES[kind].label)}</p>
      <dl class="kv">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
      ${p.notes ? `<p class="card__text" style="direction:rtl;text-align:right">${esc(p.notes)}</p>` : ''}
    </div>`;
}

/* --- שכבת הנוטאמים ---------------------------------------------------- */

function notamColor(n) {
  return n.low_altitude ? NOTAM_LOW : NOTAM_HIGH;
}

/**
 * משפחת הנוטאם, לפי האות הראשונה של קוד הנושא בשורת Q.
 *
 * ICAO מגדיר את האות הזאת כמשפחת הנושא: `A` מרחב אווירי, `F`/`M`/`L`/`S`
 * שדה תעופה ושירותיו, `R`/`W` הגבלות ואזהרות, והשאר עזרי ניווט
 * ומכשולים. זו חלוקה של התקן עצמו, לא המצאה שלנו.
 *
 * נוטאם שטרם הורחב אין לו שורת Q, ולכן אין לו משפחה — הוא מקבל
 * קטגוריה משלו במקום להיעלם או להיתלות בניחוש.
 */
const NOTAM_FAMILIES = {
  airspace:   { label: 'מרחב אווירי ונתיבים', letters: 'A' },
  aerodrome:  { label: 'שדות תעופה ומנחתים', letters: 'FMLS' },
  hazard:     { label: 'הגבלות ואזהרות', letters: 'RW' },
  navigation: { label: 'ניווט ומכשולים', letters: 'CINOP' },
  unknown:    { label: 'טרם הורחב', letters: '' }
};

/**
 * מצב התוקף ביחס לרגע הגלישה.
 *
 * נוטאם שנכנס לתוקף אחר הצהריים אינו רלוונטי לטיסה בבוקר, ועד היום
 * הוא נראה בדיוק כמו נוטאם פעיל. ההבחנה נעשית מול השעון של הדפדפן,
 * ולכן היא נכונה לרגע הצפייה ולא לרגע המשיכה.
 *
 * `unknown` אינו "כנראה פעיל" — הוא בדיוק מה שכתוב: אין זמנים, כי
 * ההודעה עדיין לא הורחבה. אסור לו להיבלע ב"פעיל".
 *
 * **מגבלה שחשוב להכיר:** החישוב מסתמך על פריטי B) ו-C) בלבד, ולא על
 * לוח הזמנים היומי ב-D). נוטאם שתקף כל היום אבל פעיל רק בין 0650
 * ל-0830 ייחשב כאן "פעיל עכשיו" גם ב-10:00. הטעות היא לכיוון
 * המחמיר — עודף אזהרה ולא חוסר — וזה הכיוון היחיד שמותר לטעות בו
 * בכלי כזה. לוח הזמנים המלא מוצג בכרטיס.
 */
const NOTAM_STATES = {
  active:  { label: 'פעיל עכשיו' },
  future:  { label: 'עתידי' },
  unknown: { label: 'ללא זמנים' }
};

function notamState(n, now) {
  const from = n.valid_from && n.valid_from.iso ? Date.parse(n.valid_from.iso) : null;
  if (!from || isNaN(from)) return 'unknown';
  if (from > now) return 'future';
  const permanent = n.valid_to && n.valid_to.permanent;
  const to = n.valid_to && n.valid_to.iso ? Date.parse(n.valid_to.iso) : null;
  if (!permanent && to && !isNaN(to) && to < now) return 'future';   // הסתיים — מטופל בסינון המקור
  return 'active';
}

function notamFamily(n) {
  const code = n.q && n.q.subject_code;
  if (!code) return 'unknown';
  const letter = code[0].toUpperCase();
  for (const [key, family] of Object.entries(NOTAM_FAMILIES)) {
    if (family.letters.includes(letter)) return key;
  }
  return 'navigation';
}

function renderNotams(notams) {
  let drawn = 0;
  if (!map) return drawn;

  const now = Date.now();

  notams.forEach((n) => {
    const state = notamState(n, now);

    const geo = n.geo;
    const color = notamColor(n);
    // עתידי נסוג ויזואלית — שקיפות וקו דק — אבל **שומר על הצבע**.
    // הצבע מסמן גובה, וזה נתון בטיחותי שאסור לו להשתנות לפי שעון.
    const faded = state === 'future';

    // הגבול המפורש שבגוף ההודעה גובר על הכול. זה האזור עצמו, לא
    // מעטפת שמקיפה אותו, ולכן הוא מצויר מלא ככל אזור אמיתי אחר.
    let shape = null;
    if (n.area) {
      shape = L.polygon(n.area.map(([lon, lat]) => [lat, lon]), {
        pane: 'notam',
        color, weight: faded ? 2 : 3, opacity: faded ? 0.5 : 1,
        dashArray: faded ? '3 7' : '8 6',
        fillColor: color, fillOpacity: faded ? 0.06 : 0.16
      });
    } else if (!geo || geo.fir_wide) {
      // רדיוס 999 = כל ה-FIR. אין מה לצייר; תג ברשימה בלבד.
      return;
    } else if (geo.radius_nm >= ENVELOPE_NM) {
      // מעטפת רחבה בלי גבול מפורש — אין כאן צורה לצייר, רק מספר
      // שמקיף את אזור ההשפעה. ציור שלה טוען טענה שגויה על השטח,
      // מצפין את המפה, וחוסם לחיצות. הנוטאם נשאר ברשימה במלואו.
      return;
    } else if (geo.radius_nm > 0) {
      shape = L.circle([geo.lat, geo.lon], {
        pane: 'notam',
        radius: geo.radius_nm * NM_TO_M,
        color, weight: faded ? 2 : 3, opacity: faded ? 0.5 : 1,
        dashArray: faded ? '3 7' : '8 6',
        fillColor: color, fillOpacity: faded ? 0.04 : 0.1
      });
    } else {
      shape = L.circleMarker([geo.lat, geo.lon], {
        pane: 'notam', radius: faded ? 6 : 8,
        color, weight: faded ? 2 : 3, opacity: faded ? 0.5 : 1,
        fillColor: color, fillOpacity: faded ? 0.15 : 0.35
      });
    }

    shape.bindPopup(notamPopup(n), { maxWidth: 260, minWidth: 200 });
    register(shape, notamLayer, { notam: notamFamily(n), state });
    if (n.id) notamShapes.set(n.id, shape);
    drawn += 1;
  });

  return drawn;
}

/**
/**
 * חלונית מפה — מכוונת להיות קטנה.
 *
 * הגרסה הראשונה הציגה כאן את הכרטיס המלא, והוא חנק את המפה: בדיוק
 * ברגע שרוצים לראות היכן האזור יושב ביחס לסביבה, החלונית מכסה אותה.
 * לכן כאן רק מה שמזהה את הנוטאם, וכפתור שקופץ לכרטיס המלא ברשימה.
 */
function notamPopup(n) {
  const subject = subjectText(n);
  const rows = [];
  const from = fmtStamp(n.valid_from, null);
  if (from) rows.push(['מ־', from]);
  const until = fmtStamp(n.valid_to, null);
  if (until) rows.push(['עד', until]);
  rows.push(['גבהים', altitudeText(n)]);

  const anchor = n.id ? 'notam-' + n.id.replace(/[^A-Za-z0-9]/g, '-') : null;
  return `
    <div class="popup">
      <div class="card__id">${esc(n.id || 'ללא מזהה')}</div>
      ${subject ? `<p class="popup__subject">${esc(subject)}</p>` : ''}
      <dl class="kv kv--tight">${rows.map(([k, v]) =>
        `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
      ${n.area ? `<p class="popup__terms">
        הגבול מגיע מרשימת הקודקודים שבגוף ההודעה — האזור עצמו,
        ולא עיגול שמקיף אותו.
      </p>` : ''}
      ${anchor ? `<button type="button" class="popup__jump" data-jump="${esc(anchor)}">פרטים מלאים ↓</button>` : ''}
    </div>`;
}

/**
 * קפיצה מהחלונית אל הכרטיס המלא ברשימה, עם הבהוב קצר כדי שהעין
 * תמצא אותו. מאזין אחד על המסמך — החלוניות נבנות כמחרוזות.
 */
function wireJumpButtons() {
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-jump]');
    if (!button) return;
    const target = document.getElementById(button.getAttribute('data-jump'));
    if (!target) return;
    if (map) map.closePopup();
    // הכרטיסים מקופלים. קפיצה אל כרטיס סגור הייתה נוחתת על שורה
    // אחת ונראית כאילו לא קרה כלום — אז פותחים אותו לפני הגלילה.
    const fold = target.querySelector('details');
    if (fold) fold.open = true;
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.add('notam-card--found');
    setTimeout(() => target.classList.remove('notam-card--found'), 2200);
  });
}

/* --- כרטיס נוטאם (משותף למפה ולרשימה) --------------------------------- */

/**
 * נוטאם שכל מה שיש לו הוא מעטפת רחבה, בלי גבול מפורש בגוף ההודעה.
 *
 * כשיש רשימת קודקודים ב-E) — יש אזור אמיתי, והמעטפת אינה רלוונטית.
 * רק בהיעדרה המספר של שורת Q נשאר לבדו, ואז אין מה לצייר.
 */
function isEnvelope(n) {
  return !n.area && !!n.geo && !n.geo.fir_wide && n.geo.radius_nm >= ENVELOPE_NM;
}

function badges(n) {
  const out = [];
  // מצב התוקף ראשון — זו השאלה הראשונה שמישהו בשטח שואל.
  if (notamState(n, Date.now()) === 'future') out.push(['future', 'טרם נכנס לתוקף']);
  if (n.geo && n.geo.fir_wide) out.push(['fir', 'חל על כל המרחב']);
  // מעטפת רחבה בלי גבול מפורש — לא מצוירת, ולכן הרשימה היא המקום
  // היחיד שבו היא נראית. התג חייב לומר את זה במפורש.
  else if (isEnvelope(n)) {
    out.push(['fir', `אזור רחב (מעטפת ${n.geo.radius_nm} מייל) — לא מצויר`]);
  }
  if (!n.geo) out.push(['nogeo', 'ללא מיקום על המפה']);
  if (n.low_altitude) out.push(['low', `רצפה מתחת ל-${LOW_ALTITUDE_FT.toLocaleString('he-IL')} רגל`]);
  else if (n.geo) out.push(['high', 'רצפה גבוהה']);
  if (n.valid_to && n.valid_to.permanent) out.push(['perm', 'תוקף קבוע']);
  if (n.valid_to && n.valid_to.estimated) out.push(['est', 'זמן סיום משוער']);
  if (n.cancellation) out.push(['cancel', 'הודעת ביטול']);
  if (n.administrative && !n.cancellation) out.push(['admin', 'מנהלתי']);
  return out.map(([kind, text]) =>
    `<span class="badge badge--${kind}">${esc(text)}</span>`).join('');
}

function notamCard(n, opts) {
  opts = opts || {};
  const rows = [
    ['תוקף מ־', fmtStamp(n.valid_from, NO_VALIDITY)],
    ['תוקף עד', fmtStamp(n.valid_to, NO_VALIDITY)],
    ['גבהים', altitudeText(n)]
  ];
  if (n.schedule) rows.push(['לוח זמנים', n.schedule]);
  if (n.geo && !n.geo.fir_wide) {
    rows.push(['מיקום', `${n.geo.lat.toFixed(4)}°N, ${n.geo.lon.toFixed(4)}°E · רדיוס ${n.geo.radius_nm} מייל ימי`]);
  }
  if (n.locations && n.locations.length) rows.push(['מיקומים', n.locations.join(', ')]);

  const subject = subjectText(n);
  const errors = (n.parse_errors || []).length
    ? `<p class="alert alert--warn" style="margin-top:10px">פרסור חלקי: ${esc(n.parse_errors.join('; '))}</p>`
    : '';

  // ברשימה המזהה כבר מופיע בכותרת השורה יחד עם כפתור "הצג במפה".
  const header = opts.omitId ? '' : `<div class="card__id">${esc(n.id || 'ללא מזהה')}</div>`;

  return `
    <div class="card">
      ${header}
      ${subject && !opts.omitTitle ? `<p class="card__title">${esc(subject)}</p>` : ''}
      ${n.q && n.q.subject_note
        ? `<p class="card__gloss">${esc(n.q.subject_note)}</p>` : ''}
      ${opts.omitBadges ? '' : `<div class="badges">${badges(n)}</div>`}
      <dl class="kv">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
      ${n.text ? `<p class="card__text">${esc(n.text)}</p>` : ''}
      ${errors}
      <details class="raw">
        <summary>הנוטאם הגולמי</summary>
        <pre>${esc(n.raw || '')}</pre>
      </details>
    </div>`;
}

/* --- רשימה ------------------------------------------------------------ */

function renderList(notams) {
  const list = el('notam-list');
  list.innerHTML = '';

  if (!notams.length) {
    list.innerHTML = '<li class="empty">אין נוטאמים פעילים בקובץ. ייתכן שהמשיכה טרם רצה — ראו את חותמת הזמן והתראות בראש הדף.</li>';
    return;
  }

  notams.forEach((n) => {
    const li = document.createElement('li');
    let cls = 'notam-card';
    if (n.administrative) cls += ' notam-card--admin';
    else if (n.low_altitude) cls += ' notam-card--low';
    else cls += ' notam-card--high';
    li.className = cls;
    if (n.id) li.id = 'notam-' + n.id.replace(/[^A-Za-z0-9]/g, '-');

    const canLocate = n.id && notamShapes.has(n.id);
    // הכרטיס מקופל. 128 כרטיסים פתוחים הפכו את הדף לגלילה אינסופית,
    // וכדי למצוא הודעה אחת היה צריך לעבור על כולן. הכותרת נשארת
    // גלויה תמיד — מזהה, נושא ותגיות — וזה מספיק כדי לסרוק ולהחליט.
    //
    // **זה אינו סינון.** כל 128 הפריטים כאן, בסדר מלא; רק הגוף מקופל.
    li.innerHTML = `
      <details class="notam-card__fold">
        <summary class="notam-card__head">
          <div class="notam-card__lead">
            <span class="card__id">${esc(n.id || 'ללא מזהה')}</span>
            ${subjectText(n) ? `<span class="notam-card__subject">${esc(subjectText(n))}</span>` : ''}
          </div>
          <div class="badges badges--summary">${badges(n)}</div>
        </summary>
        ${canLocate ? '<button type="button" class="locate">הצג במפה</button>' : ''}
        ${notamCard(n, { omitId: true, omitBadges: true, omitTitle: true })}
      </details>
    `;

    if (canLocate) {
      li.querySelector('.locate').addEventListener('click', () => {
        const shape = notamShapes.get(n.id);
        if (!el('toggle-notam').checked) {
          el('toggle-notam').checked = true;
          map.addLayer(notamLayer);
        }
        map.flyTo(shape.getLatLng ? shape.getLatLng() : shape.getBounds().getCenter(), 12);
        shape.openPopup();
        document.getElementById('map').scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    }

    list.appendChild(li);
  });
}

/* --- מקרא ------------------------------------------------------------- */

/**
 * לוח הבקרה — שתי רמות.
 *
 * הגרסה הקודמת שמה את מתגי השכבות בקופסה אחת ואת תגיות הסינון בשנייה,
 * ושתיהן דיברו על אותם נתונים בלי לומר מי שייך למי. עם חמש שכבות וכמה
 * צירי סינון זה הפך לשורת תגיות ארוכה בלי היררכיה.
 *
 * כאן כל שכבה היא קופסה שמכילה את הסינון שלה. הכותרת מכבה את השכבה
 * כולה; מי שרוצה לדייק פותח ונכנס. שכבה שאין לה סינון היא כותרת בלבד.
 *
 * **שום דבר כאן אינו מסתיר מידע** — רק את ציורו על המפה. הרשימה
 * שמתחת מלאה תמיד.
 */
const PANELS = [
  {
    id: 'aip',
    toggle: 'toggle-aip',
    label: 'מגבלות קבועות (פמ"ת)',
    open: true,
    on: true,
    axes: [
      {
        title: 'לפי סוג',
        prefix: 'aip',
        entries: ['prohibited', 'restricted', 'danger', 'uav', 'obstacle']
          .map((k) => [k, { label: ZONE_STYLES[k].label, color: ZONE_STYLES[k].color }])
      },
      {
        // הציר שהמשתמש ביקש: אזור שרצפתו גבוהה פחות מעניין את מי
        // שטס נמוך, ואפשר לכבות אותו ולנקות את המפה.
        title: 'לפי רצפת גובה',
        prefix: 'floor',
        entries: Object.entries(AIP_FLOORS)
      },
      {
        title: 'לפי נושא',
        prefix: 'theme',
        entries: Object.entries(AIP_THEMES)
      }
    ]
  },
  {
    id: 'notam',
    toggle: 'toggle-notam',
    label: 'מגבלות זמניות (נוטאם)',
    open: true,
    on: true,
    axes: [
      { title: 'לפי נושא', prefix: 'notam', dashed: true,
        entries: Object.entries(NOTAM_FAMILIES) },
      { title: 'לפי מצב תוקף', prefix: 'state', dashed: true,
        entries: Object.entries(NOTAM_STATES) }
    ]
  },
  { id: 'weather', toggle: 'toggle-weather', label: 'מזג אוויר (METAR / TAF / AIRMET)' },
  { id: 'cvfr', toggle: 'toggle-cvfr', label: 'נתיבי טיסה (CVFR)' },
  { id: 'ratag', toggle: 'toggle-ratag', label: 'שמורות טבע וגנים לאומיים',
    hint: 'טעינה בלחיצה' }
];

/**
 * שורת סינון — תיבת סימון, לא תגית.
 *
 * הגרסה הקודמת השתמשה בכפתורי־גלולה. הם נראו טוב אבל לא אמרו מה הם:
 * כפתור עגול שנדלק ונכבה אינו קורא כמו "מסונן/לא מסונן", וכשיש שלושה
 * צירים אחד מתחת לשני זה נהיה שדה של כפתורים בלי היררכיה.
 *
 * תיבת סימון אומרת בדיוק מה היא עושה, נגישה בלי ARIA נוסף, ומרוכזת
 * ברשימה מוזחת מתחת לתיבה הראשית — כך שרואים בעין מי הבן של מי.
 */
function subItemHtml(key, label, color, dashed) {
  const entry = sublayers.get(key);
  if (!entry) return '';
  return `
    <li>
      <label class="sub__item">
        <input type="checkbox" data-layer="${esc(key)}"${entry.on ? ' checked' : ''}>
        <span class="sub__swatch${dashed ? ' sub__swatch--dashed' : ''}"
              style="--swatch:${color}"></span>
        <span class="sub__label">${esc(label)}</span>
        <span class="sub__count">${entry.count}</span>
      </label>
    </li>`;
}

function axisHtml(axis, fallbackColor) {
  const items = axis.entries
    .map(([key, meta]) => subItemHtml(
      axis.prefix + ':' + key,
      meta.label,
      meta.color || fallbackColor,
      axis.dashed
    ))
    .filter(Boolean)
    .join('');
  if (!items) return '';
  return `
    <p class="sub__title">${esc(axis.title)}</p>
    <ul class="sub">${items}</ul>`;
}

function renderControls() {
  const html = PANELS.map((panel) => {
    const body = (panel.axes || [])
      .map((axis) => axisHtml(axis, panel.id === 'notam' ? NOTAM_HIGH : 'var(--z-other)'))
      .filter(Boolean)
      .join('');

    // שכבה בלי צירי סינון אינה נפתחת — קופסה ריקה רק מבלבלת.
    const head = `
      <span class="ctl__switch">
        <input type="checkbox" id="${panel.toggle}"${panel.on ? ' checked' : ''}>
        <span class="ctl__label">${esc(panel.label)}</span>
        <span class="switch__count" id="count-${panel.id}">${esc(panel.hint || '—')}</span>
      </span>`;

    if (!body) return `<div class="ctl ctl--flat">${head}</div>`;
    return `
      <details class="ctl"${panel.open ? ' open' : ''}>
        <summary class="ctl__head">${head}</summary>
        <div class="ctl__body">${body}</div>
      </details>`;
  }).join('');

  el('controls').innerHTML = html + `
    <p class="legend__note">
      קו מלא — מגבלה קבועה · קו מקווקו — נוטאם ·
      <span style="color:${CVFR_COLOR}">סגול</span> = פרוזדור CVFR פתוח ·
      <span style="color:${NOTAM_LOW}">ורוד</span> = רצפה מתחת
      ל-${LOW_ALTITUDE_FT.toLocaleString('he-IL')} רגל.
      נוטאם שגבולו מפורט בגוף ההודעה מצויר כאזור אמיתי; נוטאם שכל
      שיש לו הוא מעטפת מ-${ENVELOPE_NM} מייל ימי ומעלה
      <strong>אינו מצויר</strong> ומופיע ברשימה בלבד.
      נוטאם עתידי מצויר דהוי. כיבוי כאן משפיע על המפה בלבד;
      הרשימה למטה תמיד מלאה.
    </p>`;
}

/** לחיצה על תגית מכבה או מדליקה את הערך שלה בציר שלה. */
function wireControls() {
  const box = el('controls');

  box.addEventListener('change', (event) => {
    const input = event.target.closest('input[data-layer]');
    if (!input) return;
    const entry = sublayers.get(input.getAttribute('data-layer'));
    if (!entry) return;

    entry.on = input.checked;
    const off = filters.get(entry.axis) || new Set();
    entry.on ? off.delete(entry.value) : off.add(entry.value);
    filters.set(entry.axis, off);
    applyFilters();
  });

  // תיבת הסימון יושבת בתוך <summary>. בלי זה כל לחיצה עליה הייתה
  // גם מקפלת את הקופסה, וזו בדיוק הפעולה ההפוכה ממה שהתכוונו אליה.
  box.querySelectorAll('.ctl__switch').forEach((node) => {
    node.addEventListener('click', (event) => event.stopPropagation());
  });
}

/* --- מזג אוויר --------------------------------------------------------- */

/**
 * שכבה נפרדת לגמרי מהנוטאמים, עם מתג משלה. היא כבויה כברירת מחדל:
 * המשתמש נכנס לדף כדי לדעת מה מוגבל, ומזג האוויר הוא תוספת שנדלקת
 * כשרוצים אותה.
 */
function renderWeather(payload) {
  const reports = (payload && payload.reports) || [];
  setCount('weather', reports.length);
  const list = el('weather-list');
  list.innerHTML = '';

  if (!reports.length) {
    list.innerHTML = '<li class="empty">אין דיווחי מזג אוויר בקובץ.</li>';
  }

  reports.forEach((report, index) => {
    const li = document.createElement('li');
    const kind = (report.kind || '').toUpperCase();
    li.className = 'wx-card' + (kind === 'TAF' ? ' wx-card--taf' : '');
    if (report.area) li.className += ' wx-card--area';
    li.id = 'wx-' + index;
    // מקופל כמו כרטיס נוטאם, ומאותה סיבה: דיווח METAR גולמי הוא שורה
    // ארוכה של קודים, ועשרות כאלה פתוחים הם קיר. התחנה והסוג גלויים.
    li.innerHTML = `
      <details class="wx-card__fold">
        <summary class="wx-card__head">
          <span class="wx-card__station">${esc(report.station || report.id || '—')}</span>
          ${kind ? `<span class="wx-card__kind">${esc(kind)}</span>` : ''}
          ${report.area ? '<span class="wx-card__kind wx-card__kind--area">אזור על המפה</span>' : ''}
        </summary>
        <p class="wx-card__text">${esc(report.text || '')}</p>
      </details>
`;
    list.appendChild(li);
  });

  const drawn = renderWeatherAreas(reports);

  const stamp = fmtTime(payload && (payload.last_success || payload.generated_at));
  const parts = [`${reports.length} דיווחים`];
  parts.push(drawn ? `${drawn} מסומנים על המפה` : 'ללא סימון על המפה');
  if (payload && payload.source_name) parts.push(`מקור: ${payload.source_name}`);
  if (stamp) parts.push(`עדכון ${stamp}`);
  if (payload && payload.stale) parts.push('הנתונים אינם עדכניים');
  el('weather-sub').textContent = parts.join(' · ');
}

/**
 * מזג אוויר על המפה — רק AIRMET ו-SIGMET.
 *
 * METAR ו-TAF מדווחים על **תחנה**, כלומר נקודה, ומיקומה של התחנה אינו
 * מופיע בשום מקום במקור: לא בדף, לא ב-Locations.js ולא בפמ"ת הפנים־ארצי.
 * לסמן אותם על המפה היה מחייב להמציא קואורדינטות, וזה בדיוק מה שאסור
 * בשכבה שאמורה להיות אמינה. לכן הם נשארים ברשימה בלבד.
 *
 * AIRMET ו-SIGMET, לעומת זאת, נושאים את האזור בתוך הטקסט עצמו:
 *
 *   ... FCST WI N3321 E03548 - N3257 E03555 - N3018 E03435 - N3042 E03426
 *
 * זה פוליגון סגור מהמקור הרשמי, ואותו כן מציירים.
 */
function renderWeatherAreas(reports) {
  if (!map || !weatherLayer) return 0;
  weatherLayer.clearLayers();

  let drawn = 0;

  // תחנות METAR/TAF — נקודה לכל שדה תעופה שיש לו נקודת ייחוס בפמ"ת.
  // תחנה בלי מיקום פשוט לא מסומנת; זה עדיף על סימון במקום מנוחש.
  const stations = new Map();
  reports.forEach((report, index) => {
    const at = aerodromes[report.station];
    if (!at || report.area) return;
    if (!stations.has(report.station)) stations.set(report.station, { at, kinds: [], index });
    const entry = stations.get(report.station);
    if (report.kind && !entry.kinds.includes(report.kind)) entry.kinds.push(report.kind);
  });

  stations.forEach((entry, code) => {
    L.circleMarker([entry.at.lat, entry.at.lon], {
      pane: 'weather', radius: 7, weight: 2,
      color: WEATHER_COLOR, fillColor: '#ffffff', fillOpacity: 1
    })
      .bindTooltip(code, { permanent: true, direction: 'top', className: 'wx-tip' })
      .bindPopup(`
        <div class="popup">
          <div class="card__id">${esc(code)}</div>
          <p class="popup__subject">${esc(entry.kinds.join(' · ') || 'דיווח')}</p>
          <button type="button" class="popup__jump" data-jump="wx-${entry.index}">הדיווח המלא ↓</button>
        </div>`, { maxWidth: 240 })
      .addTo(weatherLayer);
    drawn += 1;
  });

  reports.forEach((report, index) => {
    if (!report.area) return;
    const ring = report.area.map(([lon, lat]) => [lat, lon]);
    L.polygon(ring, {
      pane: 'weather',
      color: WEATHER_COLOR, weight: 2, opacity: 0.9, dashArray: '2 5',
      fillColor: WEATHER_COLOR, fillOpacity: 0.08
    })
      .bindPopup(weatherPopup(report, index), { maxWidth: 260, minWidth: 200 })
      .addTo(weatherLayer);
    drawn += 1;
  });
  return drawn;
}

/* --- שמורות טבע וגנים לאומיים (רט"ג) ---------------------------------- */

/**
 * השכבה הזאת שוקלת 8.6MB, כי אסור לפשט את הגיאומטריה שלה — כך קובעים
 * תנאי השימוש של רט"ג. לכן היא **לא** נטענת עם הדף אלא רק כשמדליקים
 * אותה, ורק פעם אחת. מי שנכנס לראות מה מוגבל לא צריך לשלם על זה.
 */
let ratagLayer = null;
let ratagState = 'idle';   // idle | loading | ready | failed

/**
 * נקודות ייחוס של שדות תעופה, לפי ICAO. מגיעות מהפמ"ת ולא מהזיכרון —
 * זו הסיבה ש-METAR ו-TAF הופיעו עד היום ברשימה בלבד.
 */
let aerodromes = {};

/**
 * רשת נתיבי ה-CVFR של משרד התחבורה.
 *
 * עד עכשיו הנתיבים על המפה הגיעו **מהנוטאמים בלבד** — כלומר רק
 * נתיבים *סגורים*. הרשת הפתוחה, זו שטסים בה כשהכול תקין, לא הייתה
 * שם בכלל: בפמ"ת היא מפה מצוירת ולא נתונים.
 *
 * הקובץ עשוי לא להיות קיים — הוא נבנה מארכיון שמועלה ידנית, כי
 * ההורדה האוטומטית מ-data.gov.il מחזירה דף אתגר במקום ארכיון. היעדר
 * הקובץ אינו תקלה ואינו מצדיק אזהרה אדומה; המתג פשוט נשאר כבוי.
 */
let cvfrLayer = null;

async function loadRatag(toggle, label) {
  if (ratagState === 'loading') return;
  ratagState = 'loading';
  label.textContent = 'טוען…';

  try {
    const data = await loadJson('data/ratag-reserves.geojson');
    ratagLayer = L.geoJSON(data, {
      pane: 'ratag',
      style: {
        color: RATAG_COLOR, weight: 1.5, opacity: 0.85,
        fillColor: RATAG_COLOR, fillOpacity: 0.12
      },
      onEachFeature: (feature, layer) => {
        layer.bindPopup(ratagPopup(feature.properties || {}), { maxWidth: 280 });
      }
    });
    ratagState = 'ready';
    label.textContent = String((data.features || []).length);
    if (toggle.checked) map.addLayer(ratagLayer);
  } catch (err) {
    ratagState = 'failed';
    label.textContent = 'נכשל';
    toggle.checked = false;
    addAlert('<strong>שכבת שמורות הטבע לא נטענה.</strong> ' + esc(err.message), 'warn');
  }
}

/**
 * טוען את רשת ה-CVFR אם היא קיימת. מחזיר תווית למתג, או null.
 *
 * `null` בשקט כשהקובץ חסר. זה מצב צפוי ולא כשל: הקובץ נבנה מארכיון
 * שמועלה ידנית, ועד שהוא מועלה אין מה להציג.
 *
 * אין כאן מונה. הרשת כולה היא רשומה אחת, אז "1" היה נכון וחסר
 * תועלת; שטח בקמ"ר היה מדויק ולא ענה על שום שאלה שיש לטייס. המתג
 * הדלוק הוא כל המידע שצריך.
 */
async function loadCvfr() {
  let data;
  try {
    data = await loadJson('data/cvfr-routes.geojson');
  } catch (err) {
    return null;
  }
  const features = data.features || [];
  if (!features.length) return null;

  cvfrLayer = L.geoJSON(data, {
    pane: 'cvfr',
    // מילוי חלש מאוד. הפרוזדורים הם שטח ולא קו, אבל הם רקע למגבלות
    // ואסור להם להתחרות בהן ויזואלית.
    style: {
      color: CVFR_COLOR, weight: 1, opacity: 0.55,
      fillColor: CVFR_COLOR, fillOpacity: 0.1
    },
    onEachFeature: (feature, layer) => {
      layer.bindPopup(cvfrPopup(feature.properties || {}), { maxWidth: 260, minWidth: 200 });
    }
  });

  return true;
}

/**
 * חלונית נתיב.
 *
/**
 * חלונית פרוזדור.
 *
 * המאגר אינו נותן שמות לנתיבים — שלושת השדות היחידים הם אורך, שטח
 * ותאריך הגרסה. אין כאן מה להמציא, ואין טעם להציג מספרים שאינם עונים
 * על שאלה של טייס. מה שנשאר הוא הדבר האחד שכן חשוב: מתי הרשת פורסמה.
 */
function cvfrPopup(p) {
  const rows = [];
  const stamp = String(p.YEARMONTH || '');
  if (/^\d{6}$/.test(stamp)) {
    rows.push(['גרסת הרשת', `${stamp.slice(4)}/${stamp.slice(0, 4)}`]);
  }
  return `
    <div class="card">
      <div class="card__id">פרוזדור CVFR</div>
      <p class="popup__subject">רשת נתיבי הטיסה של משרד התחבורה</p>
      <dl class="kv kv--tight">${rows.map(([k, v]) =>
        `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
      <p class="popup__terms">
        ${esc(p.source || 'משרד התחבורה')} · להתמצאות בלבד.
        המאגר אינו נותן שמות לנתיבים.
        המקור המחייב הוא הפמ"ת והנוטאם.
      </p>
    </div>`;
}

function ratagPopup(p) {
  const rows = [];
  if (p.kind) rows.push(['סוג', p.kind]);
  if (p.status) rows.push(['סטטוס', p.status]);
  if (p.plan) rows.push(['תכנית', p.plan]);
  if (p.dunam) rows.push(['שטח', `${p.dunam.toLocaleString('he-IL')} דונם`]);
  // הגובה מגיע מנספח ה' לפמ"ת, לא מרט"ג. מוצג רק כשהשם התאים בדיוק —
  // גובה מהתאמה מנוחשת מסוכן יותר מגובה חסר.
  if (p.aip_upper_ft) {
    rows.push(['גובה מרבי (פמ"ת)',
      `${p.aip_upper_ft.toLocaleString('he-IL')} רגל · ${p.aip_id}`]);
  }

  return `
    <div class="card">
      <div class="card__id">${esc(p.name || p.name_en || 'שמורה')}</div>
      ${p.name_full && p.name_full !== p.name
        ? `<p class="card__title">${esc(p.name_full)}</p>` : ''}
      <dl class="kv kv--tight">${rows.map(([k, v]) =>
        `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
      <p class="popup__terms">
        הגבול: ${esc(p.source || 'רט"ג')}${p.aip_upper_ft
          ? ' · הגובה: פמ"ת א-17 נספח ה\'.'
          : ' · אין לאזור הזה גובה בנספח ה\', להתמצאות בלבד.'}
        <a href="data/ratag-terms.md">תנאי השימוש</a>
      </p>
    </div>`;
}

function weatherPopup(report, index) {
  return `
    <div class="popup">
      <div class="card__id">${esc(report.kind || 'מזג אוויר')}</div>
      <p class="popup__subject">${esc(report.station || report.id || '')}</p>
      <button type="button" class="popup__jump" data-jump="wx-${index}">הדיווח המלא ↓</button>
    </div>`;
}

/* --- חותמת זמן והתראות ------------------------------------------------ */

function renderFreshness(payload) {
  const box = el('freshness');
  const value = el('freshness-value');
  const note = el('freshness-note');
  box.classList.remove('freshness--loading');

  const reference = payload.last_success || payload.generated_at;
  const formatted = fmtTime(reference);

  if (!formatted) {
    box.classList.add('freshness--stale');
    value.textContent = 'לא ידוע';
    note.textContent = 'לא נמצאה חותמת זמן בקובץ הנתונים.';
    return;
  }

  const age = Date.now() - new Date(reference).getTime();
  value.textContent = formatted;
  note.textContent = `${relativeAge(age)} · שעון ישראל`;

  if (payload.stale || age > STALE_AFTER_MS) {
    box.classList.add('freshness--stale');
    note.textContent += ' · הנתונים אינם עדכניים';
  }
}

function addAlert(text, kind) {
  const div = document.createElement('div');
  div.className = 'alert' + (kind === 'warn' ? ' alert--warn' : '');
  div.innerHTML = text;
  el('alerts').appendChild(div);
}

/* --- טעינה ------------------------------------------------------------ */

async function loadJson(path) {
  const res = await fetch(path + '?t=' + Math.floor(Date.now() / 60000), { cache: 'no-cache' });
  if (!res.ok) throw new Error(`${path} — HTTP ${res.status}`);
  return res.json();
}

async function init() {
  let payload = null;
  let geojson = null;

  const hasMap = initMap();
  if (!hasMap) {
    document.getElementById('map').style.display = 'none';
    addAlert('<strong>המפה לא נטענה.</strong> ספריית המפות לא עלתה. כל הנוטאמים מופיעים ברשימה שמתחת, כולל טווחי הגובה והמיקומים.', 'warn');
  }

  const [notamResult, aipResult, weatherResult, obstacleResult, pointsResult] =
    await Promise.allSettled([
    loadJson('data/notams.json'),
    loadJson('data/aip-permanent.geojson'),
    loadJson('data/weather.json'),
    // מכשולים קבועים — נספח ד'. שמונה רשומות, שקולות כמעט כלום,
    // ולכן נטענות תמיד ולא בבקשה כמו שכבת רט"ג.
    loadJson('data/aip-obstacles.geojson'),
    // נקודות ייחוס של שדות תעופה — בלעדיהן אין איפה לסמן METAR/TAF.
    loadJson('data/aip-points.json')
  ]);

  if (notamResult.status === 'fulfilled') {
    payload = notamResult.value;
  } else {
    addAlert('<strong>לא נטענו נתוני נוטאם.</strong> קובץ <code>data/notams.json</code> חסר או פגום. המפה מציגה את שכבת הפמ"ת בלבד.');
  }
  // נקודות הייחוס חייבות להיטען **לפני** מזג האוויר — בלעדיהן אין
  // מיקום לתחנות ה-METAR/TAF.
  if (pointsResult.status === 'fulfilled') {
    aerodromes = (pointsResult.value && pointsResult.value.aerodromes) || {};
  }
  if (aipResult.status === 'fulfilled') {
    geojson = aipResult.value;
  }
  // המכשולים נוספים לאותה שכבה — הם באים מאותו פרק בפמ"ת, ומקבלים
  // קטגוריה משלהם במקרא.
  if (obstacleResult.status === 'fulfilled' && geojson) {
    geojson = {
      ...geojson,
      features: [...(geojson.features || []), ...(obstacleResult.value.features || [])]
    };
  }

  // --- שכבת הפמ"ת. זו השכבה החשובה מבין השתיים, אז חוסר בה מוכרז בקול.
  const aipCount = renderAip(geojson);
  const aipMeta = (geojson && geojson.metadata) || {};
  if (!aipCount) {
    setCount('aip', '0');
    addAlert(
      '<strong>שכבת המגבלות הקבועות (פמ"ת) אינה טעונה.</strong> ' +
      esc(aipMeta.status_he || 'הקובץ data/aip-permanent.geojson ריק. נספחי ב\' ו-ג\' טרם חולצו.') +
      ' עד שתיטען, המפה מציגה נוטאמים בלבד — וזו תמונה חלקית בהרבה.'
    );
  }

  // --- שכבת הנוטאמים
  const notams = (payload && payload.notams) || [];
  const drawn = renderNotams(notams);
  setCount('notam', notams.length);

  if (payload) {
    renderFreshness(payload);
    if (payload.stale) {
      const since = fmtTime(payload.last_success);
      addAlert(
        '<strong>המשיכה האחרונה נכשלה.</strong> מוצגים הנתונים האחרונים שהצליחו' +
        (since ? ` מ־${esc(since)}` : '') + '. ייתכן שהתמונה השתנתה מאז.'
      );
    }
    const counts = payload.counts || {};
    const extras = [];
    if (counts.fir_wide) extras.push(`${counts.fir_wide} חלים על כל המרחב`);
    // אלה אינם "חסרים" — הם פשוט חסרי צורה. חייבים להיספר בגלוי,
    // אחרת ההפרש בין 128 למספר המסומן נראה כמו נתונים שאבדו.
    const envelopes = notams.filter(isEnvelope).length;
    if (envelopes) extras.push(`${envelopes} על אזור רחב מכדי לצייר`);
    if (counts.no_geo) extras.push(`${counts.no_geo} ללא מיקום גיאוגרפי`);
    el('list-sub').textContent =
      `${notams.length} נוטאמים · ${drawn} מסומנים על המפה` +
      (extras.length ? ` · ${extras.join(' · ')}` : '') +
      '. ממוין לפי זמן תחילת תוקף, החדש למעלה.';
  } else {
    el('freshness').classList.add('freshness--stale');
    el('freshness-value').textContent = 'לא נטען';
    el('freshness-note').textContent = 'קובץ הנתונים לא נקרא.';
  }

  renderControls();
  wireControls();
  flushCounts();
  renderList(notams);
  wireJumpButtons();
  // הסדר נקבע פעם אחת אחרי הציור הראשון, ולא רק בסינון: בלי זה
  // הסדר הוא סדר הקריאה מהקובץ, והאזור הגדול שנקרא אחרון חוסם.
  orderByHitPriority();

  // מזג אוויר — שכבה עצמאית עם מתג משלה, כבויה כברירת מחדל.
  const weather = weatherResult.status === 'fulfilled' ? weatherResult.value : null;
  renderWeather(weather);
  const weatherToggle = el('toggle-weather');
  const weatherSection = el('weather-section');
  weatherToggle.addEventListener('change', (e) => {
    weatherSection.hidden = !e.target.checked;
    // אותו מתג מדליק גם את הרשימה וגם את האזורים על המפה — המשתמש
    // ביקש מתג אחד למזג אוויר, לא שניים.
    if (map && weatherLayer) {
      e.target.checked ? map.addLayer(weatherLayer) : map.removeLayer(weatherLayer);
    }
    // בלי גלילה אוטומטית. המתג יושב ליד המפה, וקפיצה למטה בלחיצה
    // עליו זורקת את המשתמש מהמפה בדיוק כשהוא רוצה לראות אותה.
    // הרשימה נפתחת במקומה; מי שרוצה אותה גולל אליה.
  });
  if (!weather) {
    weatherToggle.disabled = true;
    setCount('weather', '—');
  }

  if (!hasMap) {
    el('controls').style.display = 'none';
    return;
  }

  // --- רשת נתיבי ה-CVFR. דולקת כברירת מחדל כשהיא קיימת: זו התשובה
  //     לשאלה "איפה מותר לטוס", והיא הייתה חסרה מהמפה לגמרי.
  const cvfrToggle = el('toggle-cvfr');
  const cvfrReady = await loadCvfr();
  setCount('cvfr', cvfrReady ? '' : '—');
  if (cvfrReady) {
    map.addLayer(cvfrLayer);
    cvfrToggle.checked = true;
    cvfrToggle.addEventListener('change', (e) => {
      e.target.checked ? map.addLayer(cvfrLayer) : map.removeLayer(cvfrLayer);
    });
  } else {
    // הקובץ טרם נבנה. מתג מושבת אומר את האמת; אזהרה אדומה הייתה
    // מתארת מצב צפוי ככשל.
    cvfrToggle.checked = false;
    cvfrToggle.disabled = true;
  }

  // שמורות רט"ג — נטענות רק בהדלקה הראשונה, ואז נשמרות בזיכרון.
  const ratagToggle = el('toggle-ratag');
  const ratagLabel = el('count-ratag');
  ratagToggle.addEventListener('change', (e) => {
    if (!e.target.checked) {
      if (ratagLayer) map.removeLayer(ratagLayer);
      return;
    }
    if (ratagState === 'ready') map.addLayer(ratagLayer);
    else loadRatag(e.target, ratagLabel);
  });

  el('toggle-aip').addEventListener('change', (e) => {
    e.target.checked ? map.addLayer(aipLayer) : map.removeLayer(aipLayer);
  });
  el('toggle-notam').addEventListener('change', (e) => {
    e.target.checked ? map.addLayer(notamLayer) : map.removeLayer(notamLayer);
  });
}

init().catch((err) => {
  addAlert('<strong>שגיאה בטעינת הדף.</strong> ' + esc(err.message));
  console.error(err);
});

/* ---------------------------------------------------------------------------
   מגבלות מרחב אווירי — מטה בנימין
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

/**
 * "לא צוין" נשמע כאילו לנוטאם אין תוקף מוגדר, וזה לא נכון: יש לו תוקף,
 * הוא פשוט עוד לא נמשך. זמני התוקף נפתחים בכפתור ה-`+` באתר של רש"ת,
 * וזו בקשה נפרדת לכל הודעה — המשיכה עושה אותן בקצב מרוסן ושומרת
 * מטמון, אז הודעה חדשה מופיעה תחילה בלי זמנים.
 */
const NO_VALIDITY = 'טרם נמשך';

const el = (id) => document.getElementById(id);

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
  map.createPane('weather').style.zIndex = 405;   // מתחת למגבלות — הן החשובות
  map.createPane('aip').style.zIndex = 410;
  map.createPane('notam').style.zIndex = 420;

  aipLayer = L.layerGroup().addTo(map);
  notamLayer = L.layerGroup().addTo(map);
  // לא נוסף למפה כאן: שכבת מזג האוויר כבויה עד שהמתג נדלק.
  weatherLayer = L.layerGroup();

  // הכיסוי הורחב לכל הארץ, אבל ברירת המחדל נשארת מטה בנימין — שם
  // המשתמש עומד בשטח. שני כפתורים מחליפים בין המבטים.
  const views = L.control({ position: 'topright' });
  views.onAdd = () => {
    const box = L.DomUtil.create('div', 'view-switch');
    box.innerHTML =
      '<button type="button" data-view="home">מטה בנימין</button>' +
      '<button type="button" data-view="country">כל הארץ</button>';
    L.DomEvent.disableClickPropagation(box);
    box.addEventListener('click', (e) => {
      const view = e.target.getAttribute('data-view');
      if (view === 'home') map.setView(CENTER, ZOOM);
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
}

function renderAip(geojson) {
  const features = (geojson && geojson.features) || [];
  el('count-aip').textContent = features.length;
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
    register(shape, aipLayer, { aip: kind });
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
  unknown:    { label: 'טרם הורחב', letters: '' },
  route:      { label: 'נתיבי טיסה', letters: '' }
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

    // נתיבים — גם לנוטאם בלי גיאומטריה משורת Q.
    routeLines(n).forEach((route) => {
      const line = L.polyline(route.latlngs, {
        pane: 'notam',
        color: notamColor(n), weight: 4,
        opacity: state === 'future' ? 0.45 : 0.95,
        dashArray: state === 'future' ? '3 7' : '10 6'
      }).bindPopup(notamPopup(n, route.codes.join(' → ')), { maxWidth: 260, minWidth: 200 });
      register(line, notamLayer, { notam: 'route', state });
      drawn += 1;
    });

    const geo = n.geo;
    // רדיוס 999 = כל ה-FIR. לא מציירים — היה בולע את המפה. תג ברשימה בלבד.
    if (!geo || geo.fir_wide) return;

    const color = notamColor(n);
    // עתידי נסוג ויזואלית — שקיפות וקו דק — אבל **שומר על הצבע**.
    // הצבע מסמן גובה, וזה נתון בטיחותי שאסור לו להשתנות לפי שעון.
    const faded = state === 'future';
    const shape = geo.radius_nm > 0
      ? L.circle([geo.lat, geo.lon], {
          pane: 'notam',
          radius: geo.radius_nm * NM_TO_M,
          color, weight: faded ? 2 : 3, opacity: faded ? 0.5 : 1,
          dashArray: faded ? '3 7' : '8 6',
          fillColor: color, fillOpacity: faded ? 0.04 : 0.1
        })
      : L.circleMarker([geo.lat, geo.lon], {
          pane: 'notam', radius: faded ? 6 : 8,
          color, weight: faded ? 2 : 3, opacity: faded ? 0.5 : 1,
          fillColor: color, fillOpacity: faded ? 0.15 : 0.35
        });

    shape.bindPopup(notamPopup(n), { maxWidth: 260, minWidth: 200 });
    register(shape, notamLayer, { notam: notamFamily(n), state });
    if (n.id) notamShapes.set(n.id, shape);
    drawn += 1;
  });

  return drawn;
}

/**
 * נתיב שנוטאם סוגר, מצויר כקו.
 *
 * לפמ"ת אין טבלת נתיבים — המפה שם היא גרפיקה, לא נתונים. אבל הנוטאם
 * עצמו מנסח את הנתיב כרצף נקודות דיווח:
 *
 *     E) ULTRALIGHT AND HEL RTE CLSD EIRON-ZMGID-AFULA-TAVOR
 *
 * וכל נקודה כזאת נמצאת בטבלת נקודות הדיווח שחולצה מהפמ"ת. חיבור
 * השניים נותן את הקו האמיתי, בלי לנחש דבר.
 *
 * **הכול או כלום.** אם נקודה אחת ברצף אינה מוכרת, הנתיב אינו מצויר
 * כלל. קו שמדלג על נקודת ביניים עובר במסלול אחר לגמרי מזה שנסגר —
 * וזו טעות מסוכנת יותר מקו חסר. הכלל הזה גם מסנן לבד תפיסות שווא
 * כמו `NOTAM-AIRAC`, שאינן נתיב.
 */
const ROUTE_RE = /\b[A-Z]{5}(?:\s*-\s*[A-Z]{5})+\b/g;

function routeLines(n) {
  const text = `${n.text || ''} ${n.raw || ''}`;
  const seen = new Set();
  const lines = [];
  (text.match(ROUTE_RE) || []).forEach((match) => {
    const codes = match.split('-').map((c) => c.trim());
    const key = codes.join('-');
    if (seen.has(key)) return;
    seen.add(key);
    const latlngs = codes.map((code) => reportingPoints[code]);
    if (latlngs.some((p) => !p)) return;
    lines.push({ codes, latlngs: latlngs.map((p) => [p.lat, p.lon]) });
  });
  return lines;
}

/**
 * חלונית מפה — מכוונת להיות קטנה.
 *
 * הגרסה הראשונה הציגה כאן את הכרטיס המלא, והוא חנק את המפה: בדיוק
 * ברגע שרוצים לראות היכן האזור יושב ביחס לסביבה, החלונית מכסה אותה.
 * לכן כאן רק מה שמזהה את הנוטאם, וכפתור שקופץ לכרטיס המלא ברשימה.
 */
function notamPopup(n, routeLabel) {
  const subject = routeLabel || subjectText(n);
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
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.add('notam-card--found');
    setTimeout(() => target.classList.remove('notam-card--found'), 2200);
  });
}

/* --- כרטיס נוטאם (משותף למפה ולרשימה) --------------------------------- */

function badges(n) {
  const out = [];
  // מצב התוקף ראשון — זו השאלה הראשונה שמישהו בשטח שואל.
  if (notamState(n, Date.now()) === 'future') out.push(['future', 'טרם נכנס לתוקף']);
  if (n.geo && n.geo.fir_wide) out.push(['fir', 'חל על כל המרחב']);
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
      ${subject ? `<p class="card__title">${esc(subject)}</p>` : ''}
      <div class="badges">${badges(n)}</div>
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
    li.innerHTML = `
      <div class="notam-card__head">
        <div class="card__id">${esc(n.id || 'ללא מזהה')}</div>
        ${canLocate ? '<button type="button" class="locate">הצג במפה</button>' : ''}
      </div>
      ${notamCard(n, { omitId: true })}
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
 * המקרא הוא גם לוח הבקרה.
 *
 * הגרסה הראשונה הציגה מקרא סטטי ליד מתגי שכבה — שני אזורים שמדברים על
 * אותו דבר. כאן פריט המקרא **הוא** המתג: הצבע מסביר, המספר מכמת,
 * והלחיצה מכבה. פחות ממשק, יותר שליטה.
 */
function renderLegend() {
  const groups = [];

  const aipItems = ['prohibited', 'restricted', 'danger', 'uav', 'obstacle']
    .map((kind) => ({
      key: 'aip:' + kind,
      label: ZONE_STYLES[kind].label,
      color: ZONE_STYLES[kind].color,
      dashed: false
    }))
    .filter((item) => sublayers.has(item.key));
  if (aipItems.length) groups.push({ title: 'מגבלות קבועות', items: aipItems });

  const notamItems = Object.entries({ ...NOTAM_FAMILIES, route: { label: 'נתיבי טיסה' } })
    .map(([key, family]) => ({
      key: 'notam:' + key,
      label: family.label,
      color: NOTAM_HIGH,
      dashed: true
    }))
    .filter((item) => sublayers.has(item.key));
  if (notamItems.length) groups.push({ title: 'נוטאמים לפי נושא', items: notamItems });

  // ציר שני, חוצה נושאים: מה תקף ברגע הזה.
  const stateItems = Object.entries(NOTAM_STATES)
    .map(([key, state]) => ({
      key: 'state:' + key,
      label: state.label,
      color: key === 'future' ? 'var(--ink-soft)' : NOTAM_HIGH,
      dashed: true
    }))
    .filter((item) => sublayers.has(item.key));
  if (stateItems.length) groups.push({ title: 'נוטאמים לפי מצב תוקף', items: stateItems });

  el('legend').innerHTML = groups.map((group) => `
    <div class="legend__group">
      <span class="legend__title">${esc(group.title)}</span>
      ${group.items.map((item) => {
        const entry = sublayers.get(item.key);
        return `
        <button type="button" class="legend__item" data-layer="${esc(item.key)}"
                aria-pressed="${entry.on}" style="--swatch:${item.color}">
          <span class="legend__swatch${item.dashed ? ' legend__swatch--dashed' : ''}"></span>
          <span class="legend__label">${esc(item.label)}</span>
          <span class="legend__count">${entry.count}</span>
        </button>`;
      }).join('')}
    </div>`).join('') + `
    <p class="legend__note">
      קו מלא — מגבלה קבועה · קו מקווקו — נוטאם ·
      <span style="color:${NOTAM_LOW}">ורוד</span> = רצפה מתחת
      ל-${LOW_ALTITUDE_FT.toLocaleString('he-IL')} רגל.
      נוטאם עתידי מצויר דהוי. "פעיל עכשיו" לפי תוקף כללי בלבד —
      לוח הזמנים היומי מופיע בכרטיס. כיבוי משפיע על המפה בלבד;
      הרשימה למטה תמיד מלאה.
    </p>`;
}

/** לחיצה על פריט מקרא מכבה או מדליקה את התת־שכבה שלו. */
function wireLegend() {
  el('legend').addEventListener('click', (event) => {
    const button = event.target.closest('[data-layer]');
    if (!button) return;
    const key = button.getAttribute('data-layer');
    const entry = sublayers.get(key);
    if (!entry) return;

    entry.on = !entry.on;
    const off = filters.get(entry.axis) || new Set();
    entry.on ? off.delete(entry.value) : off.add(entry.value);
    filters.set(entry.axis, off);
    button.setAttribute('aria-pressed', String(entry.on));
    applyFilters();
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
  el('count-weather').textContent = reports.length;
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
    li.innerHTML = `
      <div class="wx-card__head">
        <span class="wx-card__station">${esc(report.station || report.id || '—')}</span>
        ${kind ? `<span class="wx-card__kind">${esc(kind)}</span>` : ''}
        ${report.area ? '<span class="wx-card__kind wx-card__kind--area">אזור על המפה</span>' : ''}
      </div>
      <p class="wx-card__text">${esc(report.text || '')}</p>
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

/** כל נקודות הדיווח לפי קוד, לציור נתיבים שנוטאם סוגר. */
let reportingPoints = {};

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
  // הנקודות חייבות להיטען **לפני** ציור הנוטאמים — בלעדיהן אין נתיבים,
  // וגם לפני מזג האוויר, בלעדיהן אין מיקום לתחנות.
  if (pointsResult.status === 'fulfilled') {
    aerodromes = (pointsResult.value && pointsResult.value.aerodromes) || {};
    ((pointsResult.value && pointsResult.value.points) || []).forEach((point) => {
      reportingPoints[point.code] = point;
    });
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
    el('count-aip').textContent = '0';
    addAlert(
      '<strong>שכבת המגבלות הקבועות (פמ"ת) אינה טעונה.</strong> ' +
      esc(aipMeta.status_he || 'הקובץ data/aip-permanent.geojson ריק. נספחי ב\' ו-ג\' טרם חולצו.') +
      ' עד שתיטען, המפה מציגה נוטאמים בלבד — וזו תמונה חלקית בהרבה.'
    );
  }

  // --- שכבת הנוטאמים
  const notams = (payload && payload.notams) || [];
  const drawn = renderNotams(notams);
  el('count-notam').textContent = notams.length;

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

  renderLegend();
  wireLegend();
  renderList(notams);
  wireJumpButtons();

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
    if (e.target.checked) weatherSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  if (!weather) {
    weatherToggle.disabled = true;
    el('count-weather').textContent = '—';
  }

  if (!hasMap) {
    document.querySelector('.layers').style.display = 'none';
    return;
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

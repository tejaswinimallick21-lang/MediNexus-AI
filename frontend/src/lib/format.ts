/**
 * Display formatting. All amounts are USD (Synthea data is from Massachusetts) with US grouping.
 * Dates render as DD MMM YYYY.
 */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const numberFormatters = new Map<number, Intl.NumberFormat>();
function numberFormatter(decimals: number): Intl.NumberFormat {
  let f = numberFormatters.get(decimals);
  if (!f) {
    f = new Intl.NumberFormat("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    numberFormatters.set(decimals, f);
  }
  return f;
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const usdWhole = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const isNum = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

export function formatNumber(value: number | null | undefined, decimals = 0): string {
  return isNum(value) ? numberFormatter(decimals).format(value) : "—";
}

export function formatUSD(value: number | null | undefined, { whole = false } = {}): string {
  if (!isNum(value)) return "—";
  return (whole ? usdWhole : usd).format(value);
}

/** `value` is already a percentage (e.g. 4.8 → "4.8%"). */
export function formatPercent(value: number | null | undefined, decimals = 1): string {
  return isNum(value) ? `${numberFormatter(decimals).format(value)}%` : "—";
}

/** "2020-05-27", "2020-05-27T10:00:00" or a Date → "27 May 2020". Date-only strings never shift by time zone. */
export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  if (typeof value === "string") {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
    if (m) return `${m[3]} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
    value = new Date(value);
  }
  if (Number.isNaN(value.getTime())) return "—";
  const dd = String(value.getDate()).padStart(2, "0");
  return `${dd} ${MONTHS[value.getMonth()]} ${value.getFullYear()}`;
}

/** "2020-05" → "May 2020" (chart axes). */
export function formatMonth(value: string): string {
  const m = /^(\d{4})-(\d{2})/.exec(value);
  return m ? `${MONTHS[Number(m[2]) - 1]} ${m[1]}` : value;
}

const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const usdCompact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });

/** 195514 → "195.5K" (chart axes and tight tiles). */
export function formatCompact(value: number | null | undefined): string {
  return isNum(value) ? compact.format(value) : "—";
}

/** 12534916073 → "$12.5B"; amounts under $100K keep whole-dollar precision. */
export function formatUSDCompact(value: number | null | undefined): string {
  if (!isNum(value)) return "—";
  return Math.abs(value) < 100_000 ? usdWhole.format(value) : usdCompact.format(value);
}

// Backend se baat karne ke helpers. Browser "/api/..." likhta hai, Vite use backend ko bhej deta hai.

export async function api(path, options) {
  const res = await fetch("/api" + path, options);
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.json()).detail || "";
    } catch {
      /* ignore */
    }
    throw new Error("HTTP " + res.status + (detail ? ": " + detail : ""));
  }
  return res.json();
}

// Tests ne jo "test-service-xxxx" naam ki bekaar services banayi hain, unhe dashboard mein chhupate hain.
export const HIDDEN_PREFIX = "test-service-";
export const isRealService = (name) => !String(name || "").startsWith(HIDDEN_PREFIX);

// Backend ke time UTC mein hote hain (kabhi kabhi "Z" ke bina). Hum unhe UTC maan ke local time dikhate hain.
export function parseUtc(s) {
  if (!s) return null;
  const str = String(s);
  const hasZone = /Z$|[+-]\d\d:?\d\d$/.test(str);
  return new Date(hasZone ? str : str + "Z");
}

export function fmtDateTime(s) {
  const d = parseUtc(s);
  if (!d || isNaN(d)) return "-";
  return d.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function fmtDate(s) {
  const d = parseUtc(s);
  if (!d || isNaN(d)) return "-";
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

// Chart ke x-axis ke liye (milliseconds timestamp se)
export const fmtAxis = (ts) =>
  new Date(ts).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

export const pct = (x, digits = 1) => ((Number(x) || 0) * 100).toFixed(digits) + "%";
export const num = (x) => (Number(x) || 0).toLocaleString("en-IN");

// Chart mein lagbhag 160 points se zyada na hon, isliye time range ke hisaab se bucket size chuno.
export function pickInterval(hours) {
  const options = [5, 15, 30, 60, 120, 180, 360, 720, 1440];
  return options.find((m) => (hours * 60) / m <= 160) || 1440;
}
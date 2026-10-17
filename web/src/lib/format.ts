export const fmtNum = (n: number | null | undefined, d = 0) =>
  n == null || Number.isNaN(n) ? '–' : n.toLocaleString('en-IN', { maximumFractionDigits: d, minimumFractionDigits: d })

/** 1,23,456 -> "1.2 lakh" / "3.4 cr" (Indian grouping) */
export function fmtCompact(n: number | null | undefined, d = 1): string {
  if (n == null || Number.isNaN(n)) return '–'
  const a = Math.abs(n)
  if (a >= 1e7) return (n / 1e7).toFixed(d) + ' cr'
  if (a >= 1e5) return (n / 1e5).toFixed(d) + ' lakh'
  if (a >= 1e3) return (n / 1e3).toFixed(d) + ' k'
  return String(Math.round(n))
}
export const fmtPct = (n: number | null | undefined, d = 0, sign = false) =>
  n == null ? '–' : `${sign && n > 0 ? '+' : ''}${n.toFixed(d)}%`

/** Signed number with a true minus sign: -7.8 -> "−7.8", 3 -> "+3". */
export const fmtSigned = (v: number, digits = 1) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(digits)}`

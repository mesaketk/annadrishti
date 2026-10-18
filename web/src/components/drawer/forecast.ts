// Forecast overlays for the Trends charts. Pure readers of the district file; every field is optional and every
// helper returns null when its inputs are missing, so the charts fall back to history only.
import { PHASES, riskAt, scenarioKey, splitKey } from '../../lib/scenario'
import type { District, PhaseId } from '../../types'
import { isRabiId, outlookOf } from './outlook'

type Rec = Record<string, unknown>
const isRec = (x: unknown): x is Rec => !!x && typeof x === 'object' && !Array.isArray(x)
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

export const phaseShort = (phase: PhaseId) => PHASES.find((p) => p.id === phase)?.short ?? phase

/** Year the rain falls in, and the year the harvest is counted in: kharif_2027 -> 2027 / 2027; rabi_2026_27 -> 2026 / 2027. */
export function seasonYears(season: string | null | undefined): { rain: number; harvest: number } | null {
  const m = /(\d{4})(?:_(\d{2}))?$/.exec(season ?? '')
  if (!m) return null
  const a = +m[1]
  return { rain: a, harvest: m[2] ? Math.floor(a / 100) * 100 + +m[2] : a }
}

/** "9 %" magnitudes for a range of percentage deviations; null if the range straddles zero or collapses. */
export function rangeOf(lo: number, hi: number): { a: number; b: number } | null {
  const [l, h] = lo <= hi ? [lo, hi] : [hi, lo]
  const a = l > 0 ? Math.round(l) : h < 0 ? Math.round(-h) : null
  const b = l > 0 ? Math.round(h) : h < 0 ? Math.round(-l) : null
  return a == null || b == null || a === b ? null : { a, b }
}

// ------------------------------------------------------------------ yield
export interface YieldFc { year: number; base: number; value: number; lo: number; hi: number; shock: number; loPct: number; hiPct: number; bandFallback: boolean }
/** Expected harvest for the selected season: recent 5-year mean x (1 + shock). Band = ensemble +/- spread/2 (else +/- 5 pp). */
export function yieldForecast(d: District, season: string | null | undefined, phase: PhaseId, base: number | null): YieldFc | null {
  const yrs = seasonYears(season)
  if (!yrs || base == null || !(base > 0)) return null
  const key = scenarioKey(d, season, phase)
  const shock = num(riskAt(d, key)?.expected_yield_shock_pct)
  if (shock == null) return null
  const by = isRec(d.models) && isRec((d.models as Rec).by_scenario) ? ((d.models as Rec).by_scenario as Rec) : null
  const sm = by && (isRec(by[key]) ? by[key] : isRec(by[splitKey(key)[1]]) ? by[splitKey(key)[1]] : null)
  const spread = isRec(sm) ? num(sm.spread) : null
  const centre = (isRec(sm) ? num(sm.ensemble) : null) ?? shock
  const half = spread != null ? spread / 2 : 5
  const at = (p: number) => Math.max(0, base * (1 + p / 100))
  return { year: yrs.harvest, base, value: at(shock), lo: at(centre - half), hi: at(centre + half), shock, loPct: centre - half, hiPct: centre + half, bandFallback: spread == null }
}

// ------------------------------------------------------------------ rain
export interface RainFc { year: number; window: string; v: number; tfm: { med: number; p10: number; p90: number } | null }
export function rainForecast(d: District, season: string | null | undefined, phase: PhaseId): RainFc | null {
  const yrs = seasonYears(season)
  const o = outlookOf(d, season, phase)
  if (!yrs || !o || o.rain_anom_pct == null) return null
  const rabi = isRabiId(season)
  const tfm = !rabi && o.timesfm_rain_anom_pct != null && o.timesfm_p10 != null && o.timesfm_p90 != null ? { med: o.timesfm_rain_anom_pct, p10: o.timesfm_p10, p90: o.timesfm_p90 } : null
  return { year: yrs.rain, window: o.rain_window ?? (rabi ? 'Oct–Dec' : 'Jun–Sep'), v: o.rain_anom_pct, tfm }
}

// ------------------------------------------------------------------ poshan
export const addMonths = (ym: string, n: number): string => {
  const m = /^(\d{4})-(\d{2})/.exec(ym)
  if (!m) return ym
  const t = +m[1] * 12 + (+m[2] - 1) + n
  return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`
}
const monthIndex = (ym: string) => { const m = /^(\d{4})-(\d{2})/.exec(ym); return m ? +m[1] * 12 + +m[2] - 1 : NaN }

export interface PoshanFc { target: number; end: string; points: { m: string; v: number }[] }
/** Linear 6-month projection to models.timesfm.poshan_6m_forecast_pct, from the last observed month. */
export function poshanForecast(d: District, lastMonth: string, lastValue: number): PoshanFc | null {
  const tf = isRec(d.models) && isRec((d.models as Rec).timesfm) ? ((d.models as Rec).timesfm as Rec) : null
  const target = num(tf?.poshan_6m_forecast_pct)
  if (target == null) return null
  const asOf = (d.nutrition?.poshan_live as unknown as Rec | null)?.as_of
  const anchor = typeof asOf === 'string' && /^\d{4}-\d{2}/.test(asOf) ? asOf.slice(0, 7) : lastMonth
  const end = addMonths(anchor, 6)
  const n = monthIndex(end) - monthIndex(lastMonth)
  if (!(n >= 1 && n <= 12)) return null
  return { target, end, points: Array.from({ length: n }, (_, i) => ({ m: addMonths(lastMonth, i + 1), v: lastValue + ((target - lastValue) * (i + 1)) / n })) }
}

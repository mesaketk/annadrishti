// Addendum I readers: crops.by_season and season_outlook. Every field is optional and parsed defensively;
// callers fall back to the pre-Addendum-I behaviour when the blocks are absent.
import type { CropTop, District, Kpis, Lang, PhaseId } from '../../types'
import { t } from './i18n'

export const isRabiId = (season: string | null | undefined) => !!season && /^rabi/i.test(season)

export interface OutlookPhase {
  rain_anom_pct?: number | null
  rain_window?: string | null
  p_deficit_gt10?: number | null
  tmax_anom_c?: number | null
  heat_window?: string | null
  onset_delay_days?: number | null
  timesfm_rain_anom_pct?: number | null
  timesfm_p10?: number | null
  timesfm_p90?: number | null
  plain?: string | null
}
const isRec = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x)
const numOr = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** Outlook block for the selected season and phase (falls back: exact phase -> current -> elnino). */
export function outlookOf(d: District | null | undefined, season: string | null | undefined, phase: PhaseId): OutlookPhase | null {
  const so = (d as unknown as { season_outlook?: unknown } | null | undefined)?.season_outlook
  if (!isRec(so) || !season) return null
  const s = so[season]
  if (!isRec(s)) return null
  const p = [phase, 'current', 'elnino'].map((k) => s[k]).find(isRec)
  if (!p) return null
  const o: OutlookPhase = {}
  for (const k of ['rain_anom_pct', 'p_deficit_gt10', 'tmax_anom_c', 'onset_delay_days', 'timesfm_rain_anom_pct', 'timesfm_p10', 'timesfm_p90'] as const) o[k] = numOr(p[k])
  for (const k of ['rain_window', 'heat_window', 'plain'] as const) o[k] = typeof p[k] === 'string' && p[k] ? (p[k] as string) : null
  return o
}

/** Crops to offer for the selected season: crops.by_season.<kharif|rabi>.top, else crops.top. */
export function cropsForSeason(d: District, season: string | null | undefined): CropTop[] {
  const bs = (d.crops as unknown as { by_season?: unknown } | null)?.by_season
  const kind = isRabiId(season) ? 'rabi' : season ? 'kharif' : d.main_season === 'OND' ? 'rabi' : 'kharif'
  const blk = isRec(bs) ? bs[kind] : null
  const top = isRec(blk) && Array.isArray(blk.top) ? (blk.top as CropTop[]).filter((c) => c && typeof c.crop === 'string') : []
  return top.length ? top : d.crops?.top ?? []
}

// ------------------------------------------------------------------ plain outlook sentence
type EnsoKey = 'elnino' | 'neutral' | 'lanina'
const ensoOf = (phase: PhaseId): EnsoKey | null => (phase === 'elnino' || phase === 'elnino_strong' ? 'elnino' : phase === 'neutral' ? 'neutral' : phase === 'lanina' ? 'lanina' : null)

/** Probability that the selected phase happens (for "current" the most likely phase). */
function probFor(kpis: Kpis | null | undefined, season: string | null | undefined, phase: PhaseId): { key: EnsoKey; p: number | null } {
  const probs = season ? kpis?.outlook?.enso?.p_by_season?.[season] : undefined
  let key = ensoOf(phase)
  if (!key) {
    const top = probs ? (Object.entries(probs) as [EnsoKey, number][]).sort((a, b) => b[1] - a[1])[0] : undefined
    key = top?.[0] ?? (/el ni/i.test(kpis?.enso?.state ?? '') ? 'elnino' : 'neutral')
  }
  const p = probs?.[key]
  return { key, p: typeof p === 'number' ? p : null }
}
export const levelOf = (p: number | null): 'vl' | 'l' | 'p' => (p != null && p >= 0.8 ? 'vl' : p != null && p >= 0.5 ? 'l' : 'p')

/**
 * One plain sentence for the farmer / season card. English prefers the pipeline's `plain` text; hi, mr and te use
 * the localised templates built from the same rule (>= 0.8 very likely, 0.5-0.8 likely, else possible).
 */
export function plainOutlook(lang: Lang, d: District | null | undefined, kpis: Kpis | null | undefined, season: string | null | undefined, phase: PhaseId): string {
  const o = outlookOf(d, season, phase)
  const local = lang === 'hi' || lang === 'mr' || lang === 'te'
  if (o?.plain && !local) return o.plain
  const { key, p } = probFor(kpis, season, phase)
  if (key === 'neutral') return t(lang, 'outlook.neutral')
  const rabi = isRabiId(season) || (!season && d?.main_season === 'OND')
  return t(lang, `outlook.${key}.${rabi ? 'rabi' : 'kharif'}.${levelOf(p)}`)
}

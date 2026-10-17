// Defensive readers for the Addendum D blocks (markets / groundwater / poshan_live / crops.economics).
// Everything may be absent, null, string-encoded JSON, or use the short or `prefixed` key names.
import type { District, Department, FarmerProfile, Holding, Water, Lang } from '../types'

type Rec = Record<string, unknown>
const isRec = (x: unknown): x is Rec => typeof x === 'object' && x !== null && !Array.isArray(x)
export const num = (x: unknown): number | null => {
  const v = typeof x === 'string' && x.trim() !== '' ? Number(x) : x
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}
const pick = (o: Rec | null | undefined, ...keys: string[]): unknown => {
  if (!o) return undefined
  for (const k of keys) if (o[k] != null) return o[k]
  return undefined
}
export function parseJson(x: unknown): unknown {
  if (typeof x !== 'string') return x
  try { return JSON.parse(x) } catch { return null }
}

/** Cheap scalar accessors for map layers (no series parsing). */
export const marketSpike = (d: District): number | null => {
  const m = d.markets as Rec | null | undefined
  return isRec(m) ? num(pick(m, 'price_elnino_spike_pct', 'elnino_spike_pct', 'spike_pct')) : null
}
export const gwStress = (d: District): number | null => {
  const g = d.groundwater as Rec | null | undefined
  return isRec(g) ? num(pick(g, 'gw_stress_idx', 'stress_idx')) : null
}

export interface MarketsView { crop: string | null; spike: number | null; vol: number | null; series: { x: string; y: number }[] }
export function marketsOf(d: District): MarketsView | null {
  const m = d.markets as Rec | null | undefined
  if (!isRec(m)) return null
  const spike = num(pick(m, 'price_elnino_spike_pct', 'elnino_spike_pct', 'spike_pct'))
  const vol = num(pick(m, 'price_volatility_idx', 'volatility_idx'))
  const raw = parseJson(pick(m, 'price_series_json', 'price_series', 'series'))
  let series: { x: string; y: number }[] = []
  if (Array.isArray(raw)) {
    series = raw.map((r, i) => {
      if (Array.isArray(r)) return { x: String(r[0]), y: num(r[1]) as number }
      if (isRec(r)) return { x: String(pick(r, 'year', 'x', 'date', 't') ?? i), y: num(pick(r, 'price', 'value', 'y', 'v')) as number }
      return { x: String(i), y: num(r) as number }
    }).filter((p) => p.y != null)
  } else if (isRec(raw)) {
    series = Object.keys(raw).sort().map((k) => ({ x: k, y: num(raw[k]) as number })).filter((p) => p.y != null)
  }
  if (spike == null && vol == null && series.length === 0) return null
  const crop = pick(m, 'crop', 'price_crop', 'commodity')
  return { crop: typeof crop === 'string' ? crop : null, spike, vol, series }
}

export interface GroundwaterView { depth: number | null; decline: number | null; stress: number | null }
export function groundwaterOf(d: District): GroundwaterView | null {
  const g = d.groundwater as Rec | null | undefined
  if (!isRec(g)) return null
  const v = {
    depth: num(pick(g, 'gw_premonsoon_depth_m', 'premonsoon_depth_m', 'depth_m')),
    decline: num(pick(g, 'gw_decline_10y_m_per_yr', 'decline_10y_m_per_yr', 'decline_m_per_yr')),
    stress: num(pick(g, 'gw_stress_idx', 'stress_idx')),
  }
  return v.depth == null && v.decline == null && v.stress == null ? null : v
}

export interface PoshanView { underweight: number | null; stunted: number | null; wasted: number | null; asOf: string | null }
export function poshanOf(d: District): PoshanView | null {
  const p = d.nutrition?.poshan_live as Rec | null | undefined
  if (!isRec(p)) return null
  const v = {
    underweight: num(pick(p, 'poshan_underweight_pct', 'underweight_pct', 'underweight')),
    stunted: num(pick(p, 'poshan_stunted_pct', 'stunted_pct', 'stunting', 'stunted')),
    wasted: num(pick(p, 'poshan_wasted_pct', 'wasted_pct', 'wasting', 'wasted')),
    asOf: (pick(p, 'poshan_as_of', 'as_of') as string | undefined) ?? null,
  }
  return v.underweight == null && v.stunted == null && v.wasted == null ? null : v
}

export interface EconRow { crop: string; cost: number | null; value: number | null; margin: number | null; tolerant: boolean }
export interface EconView { rows: EconRow[]; alternatives: string[] }
export function economicsOf(d: District): EconView | null {
  const raw = parseJson(d.crops?.economics)
  let list: unknown[] = []
  let altRaw: unknown = undefined
  if (Array.isArray(raw)) list = raw
  else if (isRec(raw)) {
    altRaw = pick(raw, 'coc_drought_tolerant_json', 'drought_tolerant', 'alternatives')
    const rows = parseJson(pick(raw, 'rows', 'top', 'crops', 'coc_json', 'items'))
    if (Array.isArray(rows)) list = rows
    else if (isRec(rows)) list = Object.entries(rows).map(([crop, v]) => (isRec(v) ? { crop, ...v } : { crop }))
    else if (!('rows' in raw)) list = Object.entries(raw).filter(([, v]) => isRec(v)).map(([crop, v]) => ({ crop, ...(v as Rec) }))
  }
  const alts = new Set<string>()
  const addAlt = (a: unknown) => {
    const p = parseJson(a)
    if (Array.isArray(p)) p.forEach((x) => { if (typeof x === 'string') alts.add(x.toLowerCase()); else if (isRec(x) && typeof x.crop === 'string') alts.add(x.crop.toLowerCase()) })
    else if (isRec(p)) Object.keys(p).forEach((k) => alts.add(k.toLowerCase()))
  }
  addAlt(altRaw)
  const rows: EconRow[] = []
  for (const r of list) {
    if (!isRec(r) || typeof r.crop !== 'string') continue
    const cost = num(pick(r, 'cost_c2_ha', 'cost_c2', 'coc_c2_ha', 'cost_ha', 'cost'))
    const value = num(pick(r, 'value_ha', 'value_per_ha', 'value', 'gross_value_ha'))
    const margin = num(pick(r, 'margin_ha', 'margin_per_ha', 'margin')) ?? (cost != null && value != null ? value - cost : null)
    const tol = pick(r, 'drought_tolerant', 'is_drought_tolerant') === true
    if (tol) alts.add(r.crop.toLowerCase())
    if (pick(r, 'coc_drought_tolerant_json')) addAlt(pick(r, 'coc_drought_tolerant_json'))
    rows.push({ crop: r.crop, cost, value, margin, tolerant: false })
  }
  rows.forEach((r) => { r.tolerant = alts.has(r.crop.toLowerCase()) })
  if (rows.length === 0) return null
  return { rows, alternatives: [...alts] }
}

// ---- farmer profile
export const HOLDINGS: { id: Holding; label: string; short: string }[] = [
  { id: 'marginal', label: 'Marginal <1 ha', short: 'marginal' },
  { id: 'small', label: 'Small 1-2 ha', short: 'small' },
  { id: 'medium_large', label: 'Medium-large >2 ha', short: 'medium-large' },
]
export const WATERS: { id: Water; label: string }[] = [
  { id: 'rainfed', label: 'Rainfed' }, { id: 'partial', label: 'Partly irrigated' }, { id: 'irrigated', label: 'Irrigated' },
]
export const DEPARTMENTS: { id: Department; label: string; short: string }[] = [
  { id: 'collector', label: 'Collector', short: 'Collector' },
  { id: 'food_civil_supplies', label: 'Food & Civil Supplies', short: 'Food & CS' },
  { id: 'agriculture', label: 'Agriculture', short: 'Agriculture' },
  { id: 'wcd_icds', label: 'WCD/ICDS', short: 'WCD/ICDS' },
  { id: 'rural_development', label: 'Rural Development', short: 'Rural Dev' },
  { id: 'health', label: 'Health', short: 'Health' },
  { id: 'animal_husbandry', label: 'Animal Husbandry', short: 'Animal Husb.' },
]
export const LANG_NAMES: Record<Lang, string> = {
  en: 'English', hi: 'Hindi', mr: 'Marathi', te: 'Telugu', bn: 'Bengali', ta: 'Tamil', kn: 'Kannada', gu: 'Gujarati', or: 'Odia',
}
export const defaultProfile = (d: District): FarmerProfile => ({
  holding: 'small', water: 'rainfed', crop: d.crops?.top?.[0]?.crop ?? 'other', livestock: false, tenant: false,
})
export const profileKey = (p: FarmerProfile) => `${p.holding}.${p.water}.${p.crop}.${+p.livestock}.${+p.tenant}`
export function profileTitle(p: FarmerProfile, lang: Lang): string {
  const h = HOLDINGS.find((x) => x.id === p.holding)?.short ?? p.holding
  const w = p.water === 'partial' ? 'partly irrigated' : p.water
  const parts = [h, w, p.crop === 'other' ? 'other crop' : p.crop]
  if (p.livestock) parts.push('livestock')
  if (p.tenant) parts.push('tenant')
  parts.push(LANG_NAMES[lang])
  return parts.join(' · ')
}

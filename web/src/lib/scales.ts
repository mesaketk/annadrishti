import type { Band, District, Kpis, ScenarioKey } from '../types'
import { gwStress, marketSpike } from './extra'
import { phaseLabel } from './scenario'
import type { IconName } from './icons'
import { M3 } from './m3'

export type LayerId =
  | 'risk' | 'yield_shock' | 'self_suff' | 'stunting' | 'anaemia'
  | 'rain_anom' | 'elnino_sens' | 'ndvi' | 'rain10d' | 'price_spike' | 'gw_stress'

export type NfhsRound = 'nfhs5' | 'nfhs6'

export interface Scale {
  kind: 'sequential' | 'diverging'
  stops: [number, string][]      // ascending by value
  unit: string
  label: string
  format: (v: number) => string
  lowLabel: string
  highLabel: string
}

export const NULL_COLOR: string = M3.outlineVariant
// Red = bad throughout. Sequential ramp: pale yellow -> deep red.
const RED_SEQ = ['#ffeeb0', '#fdc468', '#f98a3a', '#e0422c', '#9d0f1e']
// Diverging: red (bad) - neutral - blue
const DIV = ['#b2182b', '#ef6a54', '#f4f1ea', '#7fb8d9', '#2166ac']
const RISK_STOPS = ['#fff1b8', '#f6a541', '#e0422c', '#7f0d1b']
const BLUE_SEQ = ['#e8f3fb', '#a6cfe8', '#5ea4d1', '#2f74b5', '#17448a']

const ramp = (cols: string[], lo: number, hi: number): [number, string][] =>
  cols.map((c, i) => [lo + ((hi - lo) * i) / (cols.length - 1), c])

// Three semantic colours only (UX brief): low = green, watch = amber, act = M3 error red. Fill tones come from src/m3.css (via lib/m3.ts).
export const BAND_COLOR: Record<Band, string> = { low: M3.lowFill, medium: M3.watchFill, high: M3.actFill, no_data: NULL_COLOR }
// History "hit / miss" layer: hit = low-risk green, miss = act red, no loss = quiet neutral
export const HIT_COLOR = { hit: BAND_COLOR.low, miss: BAND_COLOR.high, noloss: M3.surfaceContainerHighest } as const
export const BAND_LABEL: Record<Band, string> = { low: 'Low risk', medium: 'Watch', high: 'Act now', no_data: 'No estimate' }

export interface BandThresholds { low_below: number; high_from: number }
/** Real thresholds come from kpis.band_thresholds (terciles of the El Nino scenario). */
export const DEFAULT_THRESHOLDS: BandThresholds = { low_below: 44.7, high_from: 55.7 }
export const thresholdsOf = (k: Kpis | null | undefined): BandThresholds => k?.band_thresholds ?? DEFAULT_THRESHOLDS
export const bandOf = (s: number | null | undefined, t: BandThresholds = DEFAULT_THRESHOLDS): Band | null =>
  s == null ? null : s >= t.high_from ? 'high' : s >= t.low_below ? 'medium' : 'low'

/** `needs`: layer is shown only when some district carries the field ('live' = disabled instead of hidden). */
export type LayerGroup = 'Risk' | 'Rain and crops' | 'People and food' | 'Prices and water'
export const LAYERS: { id: LayerId; name: string; icon: IconName; group: LayerGroup; hint: string; needsLive?: boolean; needs?: 'markets' | 'groundwater' }[] = [
  { id: 'risk', name: 'Food-security risk', icon: 'traffic', group: 'Risk', hint: 'Act now, watch or low risk for the selected season and outlook' },
  { id: 'yield_shock', name: 'Expected harvest change', icon: 'trending_down', group: 'Risk', hint: 'How much the foodgrain harvest may fall below the usual trend' },
  { id: 'rain_anom', name: 'Rain this season vs normal', icon: 'rainy', group: 'Rain and crops', hint: 'Latest monsoon rain compared with the normal for the district' },
  { id: 'elnino_sens', name: 'How much El Niño cuts rain', icon: 'thermostat', group: 'Rain and crops', hint: 'Average monsoon rain change in past El Niño years' },
  { id: 'ndvi', name: 'Crop greenness now (satellite)', icon: 'satellite_alt', group: 'Rain and crops', hint: 'Satellite greenness compared with a normal year', needsLive: true },
  { id: 'rain10d', name: 'Rain expected in 10 days', icon: 'umbrella', group: 'Rain and crops', hint: 'Forecast rain for the next 10 days', needsLive: true },
  { id: 'self_suff', name: 'Food grown vs food needed', icon: 'grass', group: 'People and food', hint: 'Grain a district grows compared with what its people need' },
  { id: 'stunting', name: "Children's nutrition (survey)", icon: 'child_care', group: 'People and food', hint: 'Children under 5 who are too short for their age, national health survey (NFHS)' },
  { id: 'anaemia', name: 'Children with anaemia (survey)', icon: 'bloodtype', group: 'People and food', hint: 'Children aged 6-59 months with low blood iron, national health survey (NFHS)' },
  { id: 'price_spike', name: 'Price swing risk', icon: 'payments', group: 'Prices and water', hint: 'How much foodgrain prices usually rise in El Niño years', needs: 'markets' },
  { id: 'gw_stress', name: 'Groundwater stress', icon: 'water_drop', group: 'Prices and water', hint: 'Wells and borewells running deeper or drying faster', needs: 'groundwater' },
]
export const LAYER_GROUPS: LayerGroup[] = ['Risk', 'Rain and crops', 'People and food', 'Prices and water']

export function latestYear(d: District): string | null {
  const ks = Object.keys(d.climate?.jjas_anomaly_pct ?? {}).filter((k) => d.climate!.jjas_anomaly_pct[k] != null)
  return ks.length ? ks.sort()[ks.length - 1] : null
}

export function getScale(layer: LayerId, nfhs: NfhsRound = 'nfhs5', thr: BandThresholds = DEFAULT_THRESHOLDS): Scale {
  const r = nfhs === 'nfhs6' ? 'NFHS-6' : 'NFHS-5'
  switch (layer) {
    case 'risk':
      // anchored at the band thresholds so low / medium / high are visually distinct
      return {
        kind: 'sequential',
        stops: [[0, RISK_STOPS[0]], [thr.low_below, RISK_STOPS[1]], [thr.high_from, RISK_STOPS[2]], [100, RISK_STOPS[3]]],
        unit: '', label: 'Food-security risk', format: (v) => v.toFixed(0), lowLabel: 'Low risk', highLabel: 'Act now',
      }
    case 'yield_shock':
      // diverging around 0 = neutral grey; negative (loss) = red
      return {
        kind: 'diverging',
        stops: [[-40, '#7f0d1b'], [-20, '#d7362a'], [-8, '#f08a5d'], [0, '#c9ced8'], [10, '#7fb8d9']],
        unit: '%', label: 'Expected harvest change vs usual', format: (v) => (v > 0 ? '+' : '') + v.toFixed(0) + '%', lowLabel: 'Harvest falls', highLabel: 'Harvest grows',
      }
    case 'self_suff':
      return { kind: 'diverging', stops: [[0.3, DIV[0]], [0.65, DIV[1]], [1, DIV[2]], [1.4, DIV[3]], [2, DIV[4]]], unit: 'x', label: 'Food grown vs food needed', format: (v) => v.toFixed(1) + 'x', lowLabel: 'Grows less than needed', highLabel: 'Grows more than needed' }
    case 'stunting':
      return { kind: 'sequential', stops: ramp(RED_SEQ, 10, 50), unit: '%', label: `Children too short for their age (${r})`, format: (v) => v.toFixed(0) + '%', lowLabel: 'Fewer children', highLabel: 'More children' }
    case 'anaemia':
      return { kind: 'sequential', stops: ramp(RED_SEQ, 40, 80), unit: '%', label: `Children with anaemia (${r})`, format: (v) => v.toFixed(0) + '%', lowLabel: 'Fewer children', highLabel: 'More children' }
    case 'rain_anom':
      return { kind: 'diverging', stops: ramp(DIV, -40, 40), unit: '%', label: 'Rain this season vs normal', format: (v) => (v > 0 ? '+' : '') + v.toFixed(0) + '%', lowLabel: 'Drier than normal', highLabel: 'Wetter than normal' }
    case 'elnino_sens':
      return { kind: 'diverging', stops: ramp(DIV, -35, 35), unit: '%', label: 'Rain change in past El Niño years', format: (v) => (v > 0 ? '+' : '') + v.toFixed(0) + '%', lowLabel: 'Much drier', highLabel: 'Wetter' }
    case 'ndvi':
      return { kind: 'diverging', stops: ramp(DIV, -0.2, 0.2), unit: '', label: 'Crop greenness vs normal', format: (v) => (v > 0 ? '+' : '') + v.toFixed(2), lowLabel: 'Browner than normal', highLabel: 'Greener than normal' }
    case 'rain10d':
      return { kind: 'sequential', stops: ramp(BLUE_SEQ, 0, 80), unit: 'mm', label: 'Rain expected in next 10 days', format: (v) => v.toFixed(0) + ' mm', lowLabel: 'Little rain', highLabel: 'Heavy rain (80+ mm)' }
    case 'price_spike':
      return { kind: 'sequential', stops: ramp(RED_SEQ, -5, 25), unit: '%', label: 'Price rise in El Niño years', format: (v) => (v > 0 ? '+' : '') + v.toFixed(0) + '%', lowLabel: 'Steady prices', highLabel: 'Big price rise' }
    case 'gw_stress':
      return { kind: 'sequential', stops: ramp(RED_SEQ, 0, 1), unit: '', label: 'Groundwater stress', format: (v) => (v >= 0.67 ? 'High' : v >= 0.34 ? 'Medium' : 'Low'), lowLabel: 'Water secure', highLabel: 'Water stressed' }
  }
}

export function layerValue(d: District, layer: LayerId, scenario: ScenarioKey, nfhs: NfhsRound): number | null {
  switch (layer) {
    case 'risk': return d.risk[scenario]?.score ?? null
    case 'yield_shock': return d.risk[scenario]?.expected_yield_shock_pct ?? null
    case 'self_suff': return d.food_balance?.self_sufficiency ?? null
    case 'stunting': return d.nutrition?.[nfhs]?.stunting ?? null
    case 'anaemia': return d.nutrition?.[nfhs]?.child_anaemia ?? null
    case 'rain_anom': { const y = latestYear(d); return y ? d.climate!.jjas_anomaly_pct[y] : null }
    case 'elnino_sens': return d.climate?.elnino_mean_anomaly_pct ?? null
    case 'ndvi': return d.climate?.live?.ndvi_anom ?? null
    case 'rain10d': return d.climate?.live?.wn_10d_rain_mm ?? null
    case 'price_spike': return marketSpike(d) ?? null
    case 'gw_stress': return gwStress(d) ?? null
  }
}

function hex(c: string): [number, number, number] {
  return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]
}

export function colorFor(scale: Scale, v: number | null): string {
  if (v == null || Number.isNaN(v)) return NULL_COLOR
  const s = scale.stops
  if (v <= s[0][0]) return s[0][1]
  if (v >= s[s.length - 1][0]) return s[s.length - 1][1]
  for (let i = 1; i < s.length; i++) {
    if (v <= s[i][0]) {
      const [v0, c0] = s[i - 1], [v1, c1] = s[i]
      const t = (v - v0) / (v1 - v0)
      const a = hex(c0), b = hex(c1)
      const m = a.map((x, k) => Math.round(x + (b[k] - x) * t))
      return `rgb(${m[0]},${m[1]},${m[2]})`
    }
  }
  return NULL_COLOR
}

const LEGACY_LABEL: Record<string, string> = { neutral: 'Neutral year', elnino: 'El Niño', elnino_strong: 'Strong El Niño (2015-like)' }
/** Works for legacy keys and `<season>:<phase>` keys (see lib/scenario.ts for season labels). */
export const scenarioLabel = (s: ScenarioKey) => {
  if (LEGACY_LABEL[s]) return LEGACY_LABEL[s]
  const [a, b] = s.includes(':') ? s.split(':') : ['', s]
  return `${a ? a.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()) + ' · ' : ''}${phaseLabel(b)}`
}

export const DRIVER_LABELS: Record<string, string> = {
  rainfed_share: 'Rainfed cropland share',
  elnino_rain_deficit: 'El Niño rain deficit',
  yield_cv: 'Yield variability',
  child_stunting: 'Child stunting',
  small_marginal_share: 'Small & marginal holdings',
  low_irrigation: 'Low irrigation cover',
  pds_dependency: 'PDS dependency',
  food_deficit: 'Local food deficit',
  crop_concentration: 'Crop concentration',
  clim_vuln_index: 'Climate vulnerability index',
}
export const driverLabel = (n: string) =>
  DRIVER_LABELS[n] ?? n.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())

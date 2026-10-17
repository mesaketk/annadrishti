// Defensive readers for Addendum E (district `models`, `kpis.models`). Everything may be absent, null or string-encoded.
import type { District, Kpis, ScenarioKey } from '../types'
import { num, parseJson } from './extra'

type Rec = Record<string, unknown>
const isRec = (x: unknown): x is Rec => typeof x === 'object' && x !== null && !Array.isArray(x)
const rec = (x: unknown): Rec | null => { const p = parseJson(x); return isRec(p) ? p : null }
const pick = (o: Rec | null | undefined, ...keys: string[]): unknown => {
  if (!o) return undefined
  for (const k of keys) if (o[k] != null) return o[k]
  return undefined
}

export interface Weights { analog: number | null; lgbm: number | null }
export interface Skill {
  lgbmRho: number | null; analogRho: number | null
  lgbmMae: number | null; analogMae: number | null; zeroMae: number | null
}
export interface TimesFm { anom: number | null; p10: number | null; p90: number | null; variant: string | null; districtSkill: string | null }

function weightsOf(m: Rec | null): Weights | null {
  const w = rec(pick(m, 'weights'))
  if (!w) return null
  const v = { analog: num(w.analog), lgbm: num(w.lgbm) }
  return v.analog == null && v.lgbm == null ? null : v
}
function skillOf(m: Rec | null): Skill | null {
  const s = rec(pick(m, 'skill')) ?? m
  if (!s) return null
  const v: Skill = {
    lgbmRho: num(pick(s, 'lgbm_rho_loyo', 'lgbm_rho')), analogRho: num(pick(s, 'analog_rho_loyo', 'analog_rho')),
    lgbmMae: num(pick(s, 'lgbm_mae')), analogMae: num(pick(s, 'analog_mae')), zeroMae: num(pick(s, 'zero_mae')),
  }
  return Object.values(v).every((x) => x == null) ? null : v
}
function timesfmOf(m: Rec | null): TimesFm | null {
  const t = rec(pick(m, 'timesfm'))
  if (!t) return null
  const v: TimesFm = {
    anom: num(pick(t, 'jjas2027_anom_pct', 'anom_pct')), p10: num(t.p10), p90: num(t.p90),
    variant: typeof t.variant === 'string' ? t.variant : null,
    districtSkill: typeof t.district_skill === 'string' ? t.district_skill : null,
  }
  return v.anom == null ? null : v
}

/** Global (kpis.models) view: skill table, weights, TimesFM national summary. */
export interface GlobalModels { weights: Weights | null; skill: Skill | null; timesfm: TimesFm | null }
export function globalModelsOf(k: Kpis | null): GlobalModels | null {
  const m = rec(k?.models)
  if (!m) return null
  const v = { weights: weightsOf(m), skill: skillOf(m), timesfm: timesfmOf(m) }
  return v.weights || v.skill || v.timesfm ? v : null
}

export interface ScenarioModel { analog: number | null; lgbm: number | null; ensemble: number | null; spread: number | null }
export interface DistrictModels { scenario: ScenarioModel | null; weights: Weights | null; skill: Skill | null; timesfm: TimesFm | null }

/** Per-district block, with kpis.models as fallback for weights/skill/timesfm. */
export function districtModelsOf(d: District, sc: ScenarioKey, k: Kpis | null): DistrictModels | null {
  const m = rec(d.models)
  if (!m) return null
  const bs = rec(pick(m, 'by_scenario'))
  const raw = rec(pick(bs, sc, sc.includes(':') ? sc.split(':')[1] : sc))
  let scenario: ScenarioModel | null = null
  if (raw) {
    const s = { analog: num(raw.analog), lgbm: num(raw.lgbm), ensemble: num(raw.ensemble), spread: num(raw.spread) }
    if (s.analog != null || s.lgbm != null || s.ensemble != null) scenario = s
  }
  const g = globalModelsOf(k)
  const v = { scenario, weights: weightsOf(m) ?? g?.weights ?? null, skill: skillOf(m) ?? g?.skill ?? null, timesfm: timesfmOf(m) ?? g?.timesfm ?? null }
  return v.scenario || v.timesfm ? v : null
}

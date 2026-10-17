// Season x phase scenario selection (Addendum F). One place decides which `risk` key is effective.
import type { District, Kpis, OutlookSeason, PhaseId, ScenarioKey, ScenarioKpis } from '../types'

export const PHASES: { id: PhaseId; label: string; short: string }[] = [
  { id: 'current', label: 'Current outlook (ENSO-weighted)', short: 'Current outlook' },
  { id: 'lanina', label: 'La Niña', short: 'La Niña' },
  { id: 'neutral', label: 'Neutral', short: 'Neutral' },
  { id: 'elnino', label: 'El Niño', short: 'El Niño' },
  { id: 'elnino_strong', label: 'Strong El Niño', short: 'Strong El Niño' },
]
const PHASE_IDS = PHASES.map((p) => p.id)
export const isPhase = (x: string): x is PhaseId => (PHASE_IDS as string[]).includes(x)

const isRabi = (season: string | null | undefined) => !!season && /^rabi/i.test(season)
const DESC: Record<string, { kharif: string; rabi: string }> = {
  lanina: { kharif: 'excess rain / flood exposure', rabi: 'cooler, wetter winter' },
  neutral: { kharif: 'normal monsoon', rabi: 'normal winter' },
  elnino: { kharif: 'weak monsoon', rabi: 'warm, dry winter' },
  elnino_strong: { kharif: '2015-like', rabi: 'severe warm, dry winter' },
  current: { kharif: 'ENSO-weighted', rabi: 'ENSO-weighted' },
}
export const phaseLabel = (p: string) => PHASES.find((x) => x.id === p)?.label ?? p
export const phaseDesc = (season: string | null | undefined, p: string) => DESC[p]?.[isRabi(season) ? 'rabi' : 'kharif'] ?? ''

/** Season-qualified key if the district carries it, else the legacy alias (`phase`, else 'elnino'). */
export function scenarioKey(d: District, season: string | null | undefined, phase: PhaseId): ScenarioKey {
  if (season) { const k = `${season}:${phase}`; if (d.risk?.[k]) return k }
  return d.risk?.[phase] ? phase : 'elnino'
}

export function splitKey(key: string): [string | null, PhaseId] {
  const [a, b] = key.includes(':') ? key.split(':') : [null, key]
  return [a, isPhase(b) ? b : 'elnino']
}
/** Risk block for a raw key, falling back to its legacy phase alias. */
export const riskAt = (d: District, key: string) => d.risk?.[key] ?? d.risk?.[splitKey(key)[1]] ?? d.risk?.elnino ?? null

/** Key for global consumers (API, chat, planner): resolved against the first scored district. */
export function globalKey(districts: District[], season: string | null | undefined, phase: PhaseId): ScenarioKey {
  const d = districts.find((x) => x.risk && Object.keys(x.risk).length) ?? districts[0]
  return d ? scenarioKey(d, season, phase) : season ? `${season}:${phase}` : phase
}
/** Legacy (season-less) key for a phase: fallback for APIs/payloads that predate seasons. */
export const legacyKey = (phase: PhaseId): ScenarioKey => (phase === 'current' || phase === 'lanina' ? 'elnino' : phase)

export function seasonsOf(k: Kpis | null | undefined): OutlookSeason[] { return k?.outlook?.seasons ?? [] }
export function defaultSeason(k: Kpis | null | undefined): string | null {
  const s = seasonsOf(k)
  return (s.find((x) => x.status === 'sowing_now') ?? s[0])?.id ?? null
}
export function defaultPhase(k: Kpis | null | undefined, season: string | null): PhaseId {
  const v = season ? k?.outlook?.default_scenario?.[season] : undefined
  return v && isPhase(v) ? v : 'elnino'
}

/** Phases that actually exist in the data for a season (always includes the ones with legacy aliases). */
export function availablePhases(districts: District[], season: string | null | undefined): PhaseId[] {
  const d = districts.find((x) => x.risk && Object.keys(x.risk).length)
  if (!d) return PHASES.map((p) => p.id)
  return PHASES.map((p) => p.id).filter((p) => (season ? !!d.risk[`${season}:${p}`] : false) || (p !== 'current' && !!d.risk[p]))
}

export function scenarioText(k: Kpis | null | undefined, season: string | null | undefined, phase: PhaseId, withDesc = false): string {
  const sl = seasonsOf(k).find((s) => s.id === season)?.label
  const pl = phaseLabel(phase)
  const d = withDesc ? phaseDesc(season, phase) : ''
  return `${sl ? `${sl} · ` : ''}${pl}${d ? ` (${d})` : ''}`
}

/** Label for any raw key (legacy or `season:phase`). */
export function keyLabel(key: string, k?: Kpis | null): string {
  const [a, b] = key.includes(':') ? key.split(':') : [null, key]
  const pl = phaseLabel(b)
  const sl = a ? seasonsOf(k).find((s) => s.id === a)?.label : null
  return sl ? `${sl} · ${pl}` : b === 'elnino' && !a ? 'El Niño (current outlook)' : pl
}

/** KPI block for the selected season/phase, falling back to the legacy by_scenario (kharif alias). */
export function kpiBlock(k: Kpis | null | undefined, season: string | null, phase: PhaseId): Partial<ScenarioKpis> | null {
  const n = (v: Partial<ScenarioKpis> | undefined) => (v && typeof v.people_in_high_risk === 'number' ? v : null)
  return (season && n(k?.by_season_scenario?.[season]?.[phase])) || n(k?.by_scenario?.[legacyKey(phase)]) || null
}

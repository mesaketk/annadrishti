// Plain-language helpers: no jargon, rounded numbers, units spelled out.
import type { Band, District, Driver, Risk } from '../../types'
import { groundwaterOf } from '../../lib/extra'
import type { IconName } from '../../lib/icons'

export const NB = ' '
export const isEl = (s: unknown) => typeof s === 'string' && /el ni/i.test(s)

// ---------------------------------------------------------------- numbers
export const pct = (n: number, d = 0) => `${n.toFixed(d)}${NB}%`
const trim = (s: string) => s.replace(/\.0$/, '')
/** 54,000,000 -> "5.4 crore"; 190,000 -> "1.9 lakh"; 72,890 -> "72,890" */
export function bigNum(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return 'not known'
  const a = Math.abs(n)
  if (a >= 1e7) return `${trim((n / 1e7).toFixed(1))} crore`
  if (a >= 1e5) return `${trim((n / 1e5).toFixed(1))} lakh`
  return Math.round(n).toLocaleString('en-IN')
}
export const tonnes = (n: number) => `${bigNum(n)} tonnes`
/** Relative change in words, e.g. -7.2 -> "about 7 % below a normal year". */
export function harvestWords(v: number | null | undefined): { text: string; dir: 'down' | 'up' | 'flat' | 'na' } {
  if (v == null) return { text: 'No estimate available yet', dir: 'na' }
  if (Math.abs(v) < 1) return { text: 'about the same as a normal year', dir: 'flat' }
  const n = Math.round(Math.abs(v))
  return v < 0 ? { text: `about ${n}${NB}% below a normal year`, dir: 'down' } : { text: `about ${n}${NB}% above a normal year`, dir: 'up' }
}
export const shockPhrase = (v: number) => `${Math.round(Math.abs(v))}${NB}% ${v < 0 ? 'lower' : 'higher'}`
export function monthName(ym: string, long = false): string {
  const m = /^(\d{4})-(\d{2})/.exec(ym)
  if (!m) return ym
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return long ? `${names[+m[2] - 1]} ${m[1]}` : `${names[+m[2] - 1]} ${m[1].slice(2)}`
}
/** "by 2026-11-15" -> "by 15 Nov 2026" */
export function leadDate(s: string | null | undefined): string | null {
  if (!s) return null
  const m = /(\d{4})-(\d{2})-(\d{2})/.exec(s)
  if (!m) return s
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${/^by/i.test(s) ? 'by ' : ''}${+m[3]} ${names[+m[2] - 1]} ${m[1]}`
}

// ---------------------------------------------------------------- traffic light
export type LightKey = 'low' | 'watch' | 'act' | 'none'
export interface Light { key: LightKey; label: string; level: string }
export const LIGHTS: Record<LightKey, Light> = {
  low: { key: 'low', label: 'Low', level: 'Low risk' },
  watch: { key: 'watch', label: 'Watch', level: 'Moderate risk' },
  act: { key: 'act', label: 'Act now', level: 'High risk' },
  none: { key: 'none', label: 'No estimate', level: 'No estimate' },
}
export const lightOf = (band: Band | string | null | undefined): Light =>
  band === 'low' ? LIGHTS.low : band === 'medium' ? LIGHTS.watch : band === 'high' ? LIGHTS.act : LIGHTS.none

// ---------------------------------------------------------------- season / outlook words
export const seasonName = (id: string | null | undefined, fallback?: string | null): string | null =>
  /rabi/i.test(id ?? '') ? 'Rabi' : /kharif/i.test(id ?? '') ? 'Kharif' : fallback === 'OND' ? 'Rabi' : fallback === 'JJAS' ? 'Kharif' : null
export function seasonWhen(id: string | null | undefined, status?: string | null, fallback?: string | null): string {
  const n = seasonName(id, fallback)
  if (!n) return 'this season'
  return status === 'upcoming' ? `next ${n}` : `this ${n}`
}
export function outlookPhrase(phase: string, ensoState?: string | null): string {
  const elActive = isEl(ensoState)
  switch (phase) {
    case 'elnino': return elActive ? 'if El Niño persists' : 'in an El Niño year'
    case 'elnino_strong': return 'if El Niño is as strong as in 2015'
    case 'neutral': return 'in a normal-rain year'
    case 'lanina': return 'in a La Niña year'
    default: return elActive ? 'on the current El Niño outlook' : 'on the current outlook'
  }
}

// ---------------------------------------------------------------- drivers: icon + sentence
type Group = 'rain' | 'crops' | 'nutrition' | 'prices' | 'water' | 'heat' | 'land' | 'food' | 'satellite' | 'other'
export interface DriverParams { n?: number; n2?: number; crop?: string; year?: string; variant?: string }
export interface DriverView { name: string; icon: IconName; group: Group; short: string; sentence: string; key: string; params: DriverParams; weight: number }

const num = (re: RegExp, s: string): number | undefined => { const m = re.exec(s); return m ? Number(m[1]) : undefined }
const first = (s: string) => num(/(-?\d+(?:\.\d+)?)/, s)
const r0 = (v: number | undefined) => (v == null ? undefined : Math.round(v))

interface Def { icon: IconName; group: Group; short: string; en: (p: DriverParams) => string; params?: (label: string, d: District, r: Risk | null) => DriverParams }
const DEFS: Record<string, Def> = {
  expected_yield_loss: {
    icon: 'grass', group: 'crops', short: 'expected harvest losses',
    params: (l, _d, r) => ({ n: r0(Math.abs(r?.expected_yield_shock_pct ?? first(l) ?? 0)) }),
    en: (p) => (p.n && p.n >= 1 ? `Harvests are expected to be about ${p.n}${NB}% below a normal year.` : 'Harvests are expected to dip slightly below a normal year.'),
  },
  rain_deficit_risk: { icon: 'rainy', group: 'rain', short: 'weak monsoon rain', params: (l) => ({ n: r0(first(l)) }), en: (p) => `There is about a ${p.n}${NB}% chance that monsoon rain falls more than 10${NB}% short.` },
  rainfed_share: {
    icon: 'grass', group: 'crops', short: 'rainfed crops',
    params: (l, d) => ({ n: d.crops?.rainfed_share != null ? Math.round(d.crops.rainfed_share * 100) : r0(first(l)) }),
    en: (p) => `About ${p.n}${NB}% of farmland depends on rain alone, with no irrigation.`,
  },
  child_stunting: { icon: 'child_care', group: 'nutrition', short: 'child nutrition', params: (l) => ({ n: r0(first(l)) }), en: (p) => `${p.n}${NB}% of children under 5 are too short for their age (stunted).` },
  child_wasting: { icon: 'child_care', group: 'nutrition', short: 'child nutrition', params: (l) => ({ n: r0(first(l)) }), en: (p) => `${p.n}${NB}% of children under 5 are too thin for their height (wasted).` },
  child_anaemia: { icon: 'child_care', group: 'nutrition', short: 'child nutrition', params: (l) => ({ n: r0(first(l)) }), en: (p) => `${p.n}${NB}% of children are anaemic (low blood iron).` },
  poshan_underweight_live: { icon: 'child_care', group: 'nutrition', short: 'child nutrition', params: (l) => ({ n: r0(first(l.replace(/^[^:]*:/, ''))) }), en: (p) => `Latest anganwadi records: ${p.n}${NB}% of weighed children are underweight.` },
  terminal_heat_risk: { icon: 'thermostat', group: 'heat', short: 'late-winter heat', params: (l) => ({ n: r0(first(l)) }), en: (p) => `In ${p.n}${NB}% of similar winters, February–March heat cut the wheat and gram crop short.` },
  ndvi_stress: {
    icon: 'satellite_alt', group: 'satellite', short: 'stressed crops',
    params: (l) => { const v = first(l.replace(/\(NDVI\)/, '')) ?? 0; return { n: v, variant: v > 0.05 ? 'pos' : v < -0.05 ? 'neg' : 'norm' } },
    en: () => '', // variant sentences are built in driverView
  },
  dry_antecedent_season: {
    icon: 'rainy', group: 'rain', short: 'dry soils after last monsoon',
    params: (l) => ({ year: /\((\d{4})\)/.exec(l)?.[1], n: r0(num(/(-?\d+(?:\.\d+)?)%/, l)) }),
    en: (p) => `Last monsoon (${p.year}) brought ${Math.abs(p.n ?? 0)}${NB}% ${(p.n ?? 0) < 0 ? 'less' : 'more'} rain than normal, so soils start the season ${(p.n ?? 0) < 0 ? 'dry' : 'wet'}.`,
  },
  top_crop_share: {
    icon: 'grass', group: 'crops', short: 'reliance on one crop',
    params: (l) => ({ n: r0(first(l)), crop: /\(([^)]+)\)/.exec(l)?.[1] }),
    en: (p) => `${p.n}${NB}% of farmland grows one crop (${p.crop ?? 'the main crop'}), so one bad season hits hard.`,
  },
  weak_kharif_carryover: {
    icon: 'grass', group: 'crops', short: 'a poor last harvest',
    params: (l) => ({ year: /\((\d{4})\)/.exec(l)?.[1], n: r0(Math.abs(num(/(-?\d+(?:\.\d+)?)%/, l) ?? 0)) }),
    en: (p) => `Last Kharif's harvest (${p.year}) was ${p.n}${NB}% below trend, so families start Rabi with less seed and income.`,
  },
  small_marginal_share: { icon: 'home', group: 'land', short: 'small farms', params: (l) => ({ n: r0(first(l)) }), en: (p) => `${p.n}${NB}% of farms are smaller than 2 hectares, so families have little cushion.` },
  price_spike_risk: { icon: 'payments', group: 'prices', short: 'price swings', params: (l) => ({ crop: /main crop ([^)]+)\)/.exec(l)?.[1] }), en: (p) => `Prices of the main crop${p.crop ? ` (${p.crop})` : ''} swing a lot from year to year.` },
  yield_cv: { icon: 'grass', group: 'crops', short: 'unstable yields', params: (l) => ({ n: r0(first(l)) }), en: (p) => `Harvests swing by about ${p.n}${NB}% from one year to the next.` },
  low_self_sufficiency: { icon: 'restaurant', group: 'food', short: 'low local grain supply', params: (l) => ({ n: r0(first(l)) }), en: (p) => `The district grows only about ${p.n}${NB}% of the grain its people need.` },
  pds_dependency: { icon: 'restaurant', group: 'food', short: 'reliance on ration shops', params: (l) => ({ n: r0(first(l)) }), en: (p) => `Ration shops supply about ${p.n}${NB}% of the district's cereal needs.` },
  groundwater_stress: {
    icon: 'water_drop', group: 'water', short: 'falling groundwater',
    params: (l, d) => { const g = groundwaterOf(d); return { n: g?.depth ?? first(l), n2: g?.decline ?? undefined } },
    en: (p) => `The water table is about ${Math.round(p.n ?? 0)} m down${p.n2 ? ` and falling about ${p.n2.toFixed(1)} m a year` : ''}.`,
  },
  climate_vulnerability: { icon: 'rainy', group: 'other', short: 'climate exposure', params: (l) => ({ n: first(l) }), en: () => 'The district is highly exposed to climate stress, by the national vulnerability index.' },
}

const strip = (l: string) => l.replace(/\s*\([^)]*\)/g, '').replace(/\s+/g, ' ').trim()
export function driverView(x: Driver & { label?: string }, d: District, r: Risk | null, weight = 1): DriverView {
  const label = x.label ?? ''
  const def = DEFS[x.name]
  if (!def) {
    const nice = label ? strip(label) : x.name.replace(/_/g, ' ')
    return { name: x.name, icon: 'push_pin', group: 'other', short: x.name.replace(/_/g, ' '), sentence: nice.endsWith('.') ? nice : `${nice}.`, key: x.name, params: {}, weight }
  }
  const params = def.params ? def.params(label, d, r) : {}
  const key = x.name === 'ndvi_stress' ? `ndvi_stress.${params.variant}` : x.name
  const sentence = x.name === 'ndvi_stress'
    ? params.variant === 'neg' ? 'Satellite images show crops below normal greenness right now.' : params.variant === 'pos' ? 'Satellite images show crops greener than normal right now.' : 'Satellite images show crops looking about normal right now.'
    : def.en(params)
  return { name: x.name, icon: def.icon, group: def.group, short: def.short, sentence, key, params, weight }
}
export function driversOf(d: District, r: Risk | null): DriverView[] {
  const list = (r?.drivers ?? []) as (Driver & { label?: string })[]
  const max = Math.max(1e-6, ...list.map((x) => x.contrib))
  return list.map((x) => driverView(x, d, r, x.contrib / max))
}

// ---------------------------------------------------------------- headline
export function headline(opts: { band: Band | string | null | undefined; drivers: DriverView[]; when: string; outlook: string }): string {
  const light = lightOf(opts.band)
  if (light.key === 'none') return 'No estimate available for this district yet.'
  const shorts = [...new Set(opts.drivers.map((x) => x.short))].slice(0, 2)
  const tail = shorts.length === 0 ? '' : light.key === 'low'
    ? ` — nothing urgent, keep an eye on ${shorts[0]}.`
    : ` — mainly ${shorts.join(' and ')}.`
  return `${light.level} ${opts.when} ${opts.outlook}${tail || '.'}`
}

// ---------------------------------------------------------------- live signals in words
export function ndviWords(v: number): string {
  return v > 0.1 ? 'much greener than normal' : v > 0.05 ? 'greener than normal' : v >= -0.05 ? 'normal' : v >= -0.1 ? 'below normal' : 'much below normal'
}
export function rainWords(v: number): string {
  return Math.abs(v) < 10 ? 'close to normal' : v < 0 ? `${Math.round(-v)}${NB}% below normal` : `${Math.round(v)}${NB}% above normal`
}
export const ndviTone = (v: number): 'good' | 'ok' | 'bad' => (v < -0.05 ? 'bad' : v > 0.05 ? 'good' : 'ok')
export const rainTone = (v: number): 'good' | 'ok' | 'bad' => (v <= -25 ? 'bad' : v >= 10 ? 'good' : 'ok')

// ---------------------------------------------------------------- estimated (imputed) values
const SOURCE_WORDS: Record<string, string> = {
  state_median: 'the state median', national_median: 'the national median', neighbours_knn: 'neighbouring districts',
  neighbours_exposure: 'neighbouring districts', ee_worldpop: 'Earth Engine WorldPop satellite counts', ee_rabi_ndvi: 'Earth Engine rabi vegetation data',
}
const sourceWords = (s: string) => SOURCE_WORDS[s] ?? s.replace(/_/g, ' ')
/** Returns "Estimated from …" when any of the dotted paths (or their children) appears in data_quality.imputed. */
export function imputedNote(d: District, ...paths: string[]): string | null {
  const m = (d.data_quality as { imputed?: unknown } | null | undefined)?.imputed
  if (!m || typeof m !== 'object' || Array.isArray(m)) return null
  for (const k of Object.keys(m)) {
    if (paths.some((p) => k === p || k.startsWith(`${p}.`) || p.startsWith(`${k}.`))) return `Estimated from ${sourceWords(String((m as Record<string, unknown>)[k]))}`
  }
  return null
}

// ---------------------------------------------------------------- charts: captions
export const yearNum = (y: string) => Number(y)
export function mean(xs: number[]): number | null { return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null }

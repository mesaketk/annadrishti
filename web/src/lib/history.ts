// History mode data (Addendum H): GET /api/history (index) and /api/history/{year}; cached per year, defensive about 404.
import { useEffect, useState } from 'react'
import type { IconName } from './icons'

export interface HistEnso { phase?: string; oni_jja_son?: number | null; all_india_jjas_anom_pct?: number | null; headline?: string; n_loss_districts?: number | null; n_loss_warned?: number | null; pct_loss_warned?: number | null }
export interface HistIndex { years: number[]; enso: Record<string, HistEnso> }
export interface HistDistrict {
  rain_anom_pct?: number | null; ond_anom_pct?: number | null; yield_dev_pct?: number | null
  tool_score?: number | null; tool_band?: 'low' | 'medium' | 'high' | 'no_data' | null
  lgbm_oos_shock_pct?: number | null; warned?: boolean | null; nfhs_round?: string | null; stunting?: number | null
}
export interface HistYear { year: number; enso?: HistEnso; districts: Record<string, HistDistrict> }

export const HIST_MIN = 2003
export const HIST_MAX = 2024
export type HistoryLayerId = 'h_rain' | 'h_yield' | 'h_tool' | 'h_hit'
export const HISTORY_LAYERS: { id: HistoryLayerId; name: string; icon: IconName; hint: string }[] = [
  { id: 'h_rain', name: 'What happened: monsoon', icon: 'rainy', hint: 'Monsoon rain that year compared with normal' },
  { id: 'h_yield', name: 'What happened: harvest', icon: 'grass', hint: 'Foodgrain harvest that year compared with the usual trend' },
  { id: 'h_tool', name: 'What the tool would have said', icon: 'traffic', hint: 'The warning this tool would have given using that year\'s rain' },
  { id: 'h_hit', name: 'Hit / miss', icon: 'target', hint: 'Did the warning match what happened to the harvest?' },
]

export const LOSS_PCT = -5
export type HitKind = 'hit' | 'miss' | 'noloss' | 'nodata'
/** Warned and harvest fell >=5 % below trend = hit; no warning and loss = miss; otherwise no loss. */
export function hitKind(h: HistDistrict | undefined): HitKind {
  if (!h || h.yield_dev_pct == null) return 'nodata'
  if (h.yield_dev_pct > LOSS_PCT) return 'noloss'
  const warned = h.warned ?? (h.tool_band === 'medium' || h.tool_band === 'high')
  if (h.warned == null && !h.tool_band) return 'nodata'
  return warned ? 'hit' : 'miss'
}

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(r.status === 404 ? 'History not available yet' : `${r.status} ${r.statusText}`)
  if (!(r.headers.get('content-type') ?? '').includes('json')) throw new Error('History not available yet')
  return (await r.json()) as T
}

let indexP: Promise<HistIndex> | null = null
const yearP = new Map<number, Promise<HistYear>>()
export const loadHistoryIndex = (): Promise<HistIndex> => {
  if (!indexP) indexP = getJson<HistIndex>('/api/history').catch((e) => { indexP = null; throw e })
  return indexP
}
export const loadHistoryYear = (y: number): Promise<HistYear> => {
  let p = yearP.get(y)
  if (!p) { p = getJson<HistYear>(`/api/history/${y}`).catch((e) => { yearP.delete(y); throw e }); yearP.set(y, p) }
  return p
}
export const prefetchHistory = (years: number[]) => years.forEach((y) => { if (y >= HIST_MIN && y <= HIST_MAX) void loadHistoryYear(y).catch(() => undefined) })
export const resetHistoryCache = () => { indexP = null; yearP.clear() }

interface Async<T> { data: T | null; error: string | null; loading: boolean }
function useAsync<T>(load: (() => Promise<T>) | null, deps: unknown[]): Async<T> {
  const [st, setSt] = useState<Async<T>>({ data: null, error: null, loading: !!load })
  useEffect(() => {
    if (!load) { setSt({ data: null, error: null, loading: false }); return }
    let c = false
    setSt((s) => ({ data: s.data, error: null, loading: true }))
    load().then((data) => !c && setSt({ data, error: null, loading: false })).catch((e: Error) => !c && setSt({ data: null, error: e.message, loading: false }))
    return () => { c = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return st
}
export const useHistoryIndex = (enabled: boolean, nonce = 0) => useAsync(enabled ? loadHistoryIndex : null, [enabled, nonce])
export const useHistoryYear = (year: number, enabled: boolean, nonce = 0) => useAsync(enabled ? () => loadHistoryYear(year) : null, [year, enabled, nonce])

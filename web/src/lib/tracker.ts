// Action tracker (prototype, Addendum I): localStorage `annadrishti.tracker` = { [lgd]: TrackedAction[] }.
// Also exposed as `window.annadrishtiTracker` so the district drawer's "Add to tracker" buttons can call it without importing the shell.
import { useSyncExternalStore } from 'react'

export type TrackStatus = 'planned' | 'in_progress' | 'done'
export const STATUS_LABEL: Record<TrackStatus, string> = { planned: 'Planned', in_progress: 'In progress', done: 'Done' }
export const STATUSES: TrackStatus[] = ['planned', 'in_progress', 'done']

export interface TrackedAction {
  id: string
  action: string
  dept: string          // Department id (lib/plain DEPARTMENTS) or free text; '' = unassigned
  due: string           // YYYY-MM-DD or ''
  status: TrackStatus
  note: string
  updated_at: string    // ISO
}
export type TrackerData = Record<string, TrackedAction[]>
export type NewAction = { action: string } & Partial<Omit<TrackedAction, 'id' | 'action' | 'updated_at'>>

export interface AnnadrishtiTracker {
  /** Add an action to a district. Returns the stored item (existing one if the same action text is already tracked there). */
  add: (lgd: number, item: NewAction | string) => TrackedAction | null
  /** True if an action with this text (case-insensitive) is already tracked for the district. */
  has: (lgd: number, action: string) => boolean
  /** Actions of one district, or every district ({ [lgd]: TrackedAction[] }) when `lgd` is omitted. */
  list: ((lgd: number) => TrackedAction[]) & ((lgd?: undefined) => TrackerData)
  update: (lgd: number, id: string, patch: Partial<Omit<TrackedAction, 'id'>>) => TrackedAction | null
  remove: (lgd: number, id: string) => boolean
}
declare global { interface Window { annadrishtiTracker?: AnnadrishtiTracker } }

const KEY = 'annadrishti.tracker'
const EVT = 'annadrishti:tracker'
const isStatus = (x: unknown): x is TrackStatus => x === 'planned' || x === 'in_progress' || x === 'done'
const norm = (s: string) => s.trim().replace(/\s+/g, ' ').toLowerCase()

function load(): TrackerData {
  try {
    const raw = JSON.parse(window.localStorage.getItem(KEY) ?? '{}') as unknown
    if (!raw || typeof raw !== 'object') return {}
    const out: TrackerData = {}
    for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
      if (!Array.isArray(v)) continue
      const items = v.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object' && typeof (x as TrackedAction).action === 'string').map((x) => ({
        id: String(x.id ?? Math.random().toString(36).slice(2)), action: String(x.action), dept: String(x.dept ?? ''), due: String(x.due ?? ''),
        status: isStatus(x.status) ? x.status : 'planned', note: String(x.note ?? ''), updated_at: String(x.updated_at ?? ''),
      }))
      if (items.length) out[k] = items
    }
    return out
  } catch { return {} }
}

// snapshot is cached so useSyncExternalStore sees a stable reference until something changes
let cache: TrackerData | null = null
const snapshot = (): TrackerData => (cache ??= load())
function commit(next: TrackerData) {
  cache = next
  try { window.localStorage.setItem(KEY, JSON.stringify(next)) } catch { /* private mode: keep in memory */ }
  window.dispatchEvent(new Event(EVT))
}
const subscribe = (cb: () => void) => {
  const onStorage = (e: StorageEvent) => { if (e.key === KEY || e.key === null) { cache = null; cb() } }
  window.addEventListener(EVT, cb)
  window.addEventListener('storage', onStorage)
  return () => { window.removeEventListener(EVT, cb); window.removeEventListener('storage', onStorage) }
}

const now = () => new Date().toISOString()
const mapList = (data: TrackerData, lgd: number, f: (l: TrackedAction[]) => TrackedAction[]): TrackerData => {
  const next = { ...data, [String(lgd)]: f(data[String(lgd)] ?? []) }
  if (!next[String(lgd)].length) delete next[String(lgd)]
  return next
}

function add(lgd: number, item: NewAction | string): TrackedAction | null {
  const it: NewAction = typeof item === 'string' ? { action: item } : item
  const text = (it.action ?? '').trim()
  if (!Number.isFinite(lgd) || !text) return null
  const data = snapshot()
  const dup = (data[String(lgd)] ?? []).find((x) => norm(x.action) === norm(text))
  if (dup) return dup
  const row: TrackedAction = {
    id: `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`, action: text, dept: it.dept ?? '', due: it.due ?? '',
    status: isStatus(it.status) ? it.status : 'planned', note: it.note ?? '', updated_at: now(),
  }
  commit(mapList(data, lgd, (l) => [...l, row]))
  return row
}
const has = (lgd: number, action: string) => (snapshot()[String(lgd)] ?? []).some((x) => norm(x.action) === norm(action))
function list(lgd?: number): TrackedAction[] | TrackerData {
  const d = snapshot()
  return lgd == null ? d : d[String(lgd)] ?? []
}
function update(lgd: number, id: string, patch: Partial<Omit<TrackedAction, 'id'>>): TrackedAction | null {
  const data = snapshot()
  let out: TrackedAction | null = null
  const next = mapList(data, lgd, (l) => l.map((x) => (x.id === id ? (out = { ...x, ...patch, status: isStatus(patch.status) ? patch.status : x.status, updated_at: now() }) : x)))
  if (!out) return null
  commit(next)
  return out
}
function remove(lgd: number, id: string): boolean {
  const data = snapshot()
  if (!(data[String(lgd)] ?? []).some((x) => x.id === id)) return false
  commit(mapList(data, lgd, (l) => l.filter((x) => x.id !== id)))
  return true
}

export const tracker: AnnadrishtiTracker = { add, has, list: list as AnnadrishtiTracker['list'], update, remove }
if (typeof window !== 'undefined') window.annadrishtiTracker = tracker

export const useTracker = (): TrackerData => useSyncExternalStore(subscribe, snapshot, () => ({}))
export function trackerCounts(d: TrackerData): { total: number; done: number; open: number } {
  let total = 0, done = 0
  for (const l of Object.values(d)) for (const x of l) { total++; if (x.status === 'done') done++ }
  return { total, done, open: total - done }
}
export const useTrackerCounts = () => trackerCounts(useTracker())

/** CSV (UTF-8, quoted when needed). `names` maps lgd -> { district, state }. */
export function trackerCsv(d: TrackerData, names: (lgd: number) => { district: string; state: string } | undefined, deptLabel: (id: string) => string): string {
  const esc = (v: unknown) => (v == null ? '' : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v))
  const head = ['State', 'District', 'LGD', 'Action', 'Owner department', 'Due date', 'Status', 'Note', 'Last updated']
  const rows = Object.entries(d).flatMap(([lgd, items]) => {
    const n = names(Number(lgd))
    return items.map((x) => [n?.state ?? '', n?.district ?? '', lgd, x.action, deptLabel(x.dept), x.due, STATUS_LABEL[x.status], x.note, x.updated_at])
  }).sort((a, b) => String(a[0]).localeCompare(String(b[0])) || String(a[1]).localeCompare(String(b[1])))
  return [head, ...rows].map((r) => r.map(esc).join(',')).join('\n')
}

import { create } from 'zustand'
import type { Department, District, Kpis, Lang, PhaseId } from '../types'
import { isDept, isLang } from './plain'
import { isRole, type Role } from './route'
import { HIST_MAX, type HistoryLayerId } from './history'
import type { LayerId, NfhsRound } from './scales'
import { availablePhases, defaultPhase, defaultSeason, isPhase } from './scenario'

export type View = 'map' | 'planner'
export type Mode = 'now' | 'history'

const LS = { role: 'annadrishti.role', lang: 'annadrishti.language', dept: 'annadrishti.department', district: 'annadrishti.district' }
const read = (k: string): string | null => { try { return window.localStorage.getItem(k) } catch { return null } }
const write = (k: string, v: string | null) => { try { if (v == null) window.localStorage.removeItem(k); else window.localStorage.setItem(k, v) } catch { /* private mode */ } }
const initLang = (): Lang => { const v = read(LS.lang); return isLang(v) ? v : 'en' }
const initDept = (): Department => { const v = read(LS.dept); return isDept(v) ? v : 'collector' }
const initRole = (): Role | null => { const v = read(LS.role); return isRole(v) ? v : null }
const initLgd = (): number | null => { const v = Number(read(LS.district)); return Number.isFinite(v) && v > 0 ? v : null }

interface State {
  districts: District[]
  byLgd: Map<number, District>
  kpis: Kpis | null
  mock: boolean
  loading: boolean
  error: string | null
  setData: (d: District[], k: Kpis, mock: boolean) => void
  setError: (e: string) => void

  view: View
  setView: (v: View) => void
  season: string | null // kpis.outlook.seasons[].id; null when the payload has no outlook
  setSeason: (s: string) => void
  phase: PhaseId
  setPhase: (p: PhaseId) => void
  layer: LayerId
  setLayer: (l: LayerId) => void
  nfhs: NfhsRound
  setNfhs: (n: NfhsRound) => void
  stateFilter: string
  setStateFilter: (s: string) => void

  selected: number | null
  flyNonce: number // bumps when selection should move the camera
  select: (lgd: number | null, fly?: boolean) => void

  chatOpen: boolean
  setChatOpen: (o: boolean) => void

  // ---- audience (persisted in localStorage)
  role: Role | null
  setRole: (r: Role) => void
  language: Lang
  setLanguage: (l: Lang) => void
  department: Department
  setDepartment: (d: Department) => void
  myLgd: number | null // "my district" for the farmer and officer routes
  setMyLgd: (l: number | null) => void

  // ---- history mode (planner + officer)
  mode: Mode
  setMode: (m: Mode) => void
  year: number
  setYear: (y: number) => void
  historyLayer: HistoryLayerId
  setHistoryLayer: (l: HistoryLayerId) => void
  playing: boolean
  setPlaying: (p: boolean) => void
}

export const useStore = create<State>((set) => ({
  districts: [], byLgd: new Map(), kpis: null, mock: false, loading: true, error: null,
  setData: (districts, kpis, mock) => {
    const season = defaultSeason(kpis)
    set({ districts, kpis, mock, loading: false, error: null, byLgd: new Map(districts.map((d) => [d.lgd, d])), season, phase: defaultPhase(kpis, season) })
  },
  setError: (error) => set({ error, loading: false }),

  view: 'map', setView: (view) => set({ view }),
  season: null,
  setSeason: (season) => set((s) => {
    // keep the chosen phase if the new season has it, else fall back to that season's default
    const ok = availablePhases(s.districts, season).includes(s.phase)
    return { season, phase: ok ? s.phase : defaultPhase(s.kpis, season) }
  }),
  phase: 'elnino', setPhase: (phase) => set({ phase: isPhase(phase) ? phase : 'elnino' }),
  layer: 'risk', setLayer: (layer) => set({ layer }),
  nfhs: 'nfhs5', setNfhs: (nfhs) => set({ nfhs }),
  stateFilter: '', setStateFilter: (stateFilter) => set({ stateFilter }),

  selected: null, flyNonce: 0,
  select: (selected, fly = false) => set((s) => ({ selected, flyNonce: fly ? s.flyNonce + 1 : s.flyNonce })),

  chatOpen: false, setChatOpen: (chatOpen) => set({ chatOpen }),

  role: initRole(), setRole: (role) => { write(LS.role, role); set({ role }) },
  language: initLang(), setLanguage: (language) => { write(LS.lang, language); set({ language }) },
  department: initDept(), setDepartment: (department) => { write(LS.dept, department); set({ department }) },
  myLgd: initLgd(), setMyLgd: (myLgd) => { write(LS.district, myLgd == null ? null : String(myLgd)); set({ myLgd }) },

  mode: 'now', setMode: (mode) => set({ mode, playing: false }),
  year: HIST_MAX, setYear: (year) => set({ year }),
  historyLayer: 'h_rain', setHistoryLayer: (historyLayer) => set({ historyLayer }),
  playing: false, setPlaying: (playing) => set({ playing }),
}))

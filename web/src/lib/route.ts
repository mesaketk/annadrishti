// Tiny History-API router (no react-router dependency): /farmer, /officer, /planner.
import { useSyncExternalStore } from 'react'

export type Role = 'farmer' | 'officer' | 'planner'
export type Route = Role | 'root'
export const ROLES: Role[] = ['farmer', 'officer', 'planner']
export const isRole = (x: unknown): x is Role => ROLES.includes(x as Role)

const EVT = 'annadrishti:nav'
export const currentRoute = (): Route => {
  const p = window.location.pathname.replace(/\/+$/, '').split('/')[1] ?? ''
  return isRole(p) ? p : 'root'
}
export function navigate(to: Role | '/', replace = false) {
  const path = to === '/' ? '/' : `/${to}`
  if (window.location.pathname === path) return
  if (replace) window.history.replaceState(null, '', path)
  else window.history.pushState(null, '', path)
  window.dispatchEvent(new Event(EVT))
}
const subscribe = (cb: () => void) => {
  window.addEventListener('popstate', cb)
  window.addEventListener(EVT, cb)
  return () => { window.removeEventListener('popstate', cb); window.removeEventListener(EVT, cb) }
}
export const useRoute = (): Route => useSyncExternalStore(subscribe, currentRoute, () => 'root' as Route)

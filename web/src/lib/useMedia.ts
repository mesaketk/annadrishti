import { useSyncExternalStore } from 'react'

/** Reactive CSS media query, e.g. useMedia('(min-width: 1280px)'). */
export function useMedia(query: string): boolean {
  return useSyncExternalStore(
    (cb) => { const m = window.matchMedia(query); m.addEventListener('change', cb); return () => m.removeEventListener('change', cb) },
    () => window.matchMedia(query).matches,
    () => false,
  )
}

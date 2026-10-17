import { useCallback, useEffect, useState } from 'react'
import { getTimeseries, NO_HISTORY } from '../../lib/api'
import { useStore } from '../../lib/store'
import type { Timeseries } from '../../types'

const cache = new Map<string, Timeseries>()
export interface TsState { ts: Timeseries | null; loading: boolean; error: string | null; noHistory: boolean; retry: () => void }

/** Loads /api/timeseries/{lgd} (mock bundle in demo mode) only while `enabled`; cached per district. */
export function useTimeseries(lgd: number, enabled = true): TsState {
  const mock = useStore((s) => s.mock)
  const ck = `${mock ? 'm' : 'a'}${lgd}`
  const [state, setState] = useState<{ ts: Timeseries | null; loading: boolean; error: string | null }>({ ts: cache.get(ck) ?? null, loading: false, error: null })
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    const hit = cache.get(ck)
    if (hit) { setState({ ts: hit, loading: false, error: null }); return }
    if (!enabled) { setState({ ts: null, loading: false, error: null }); return }
    let cancelled = false
    setState({ ts: null, loading: true, error: null })
    getTimeseries(lgd, mock)
      .then((t) => { cache.set(ck, t); if (!cancelled) setState({ ts: t, loading: false, error: null }) })
      .catch((e: Error) => { if (!cancelled) setState({ ts: null, loading: false, error: e.message }) })
    return () => { cancelled = true }
  }, [lgd, mock, ck, enabled, nonce])
  const retry = useCallback(() => setNonce((n) => n + 1), [])
  return { ...state, noHistory: state.error === NO_HISTORY, retry }
}

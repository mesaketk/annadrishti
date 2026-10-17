import { useCallback, useMemo } from 'react'
import type { District } from '../types'
import { globalKey, scenarioKey, scenarioText, seasonsOf } from './scenario'
import { useStore } from './store'

/** Selected season/phase plus the effective keys: `key(d)` per district, `gkey` for API/chat/planner. */
export function useScenario() {
  const season = useStore((s) => s.season)
  const phase = useStore((s) => s.phase)
  const districts = useStore((s) => s.districts)
  const kpis = useStore((s) => s.kpis)
  const key = useCallback((d: District) => scenarioKey(d, season, phase), [season, phase])
  const gkey = useMemo(() => globalKey(districts, season, phase), [districts, season, phase])
  const seasonObj = useMemo(() => seasonsOf(kpis).find((s) => s.id === season) ?? null, [kpis, season])
  const label = useMemo(() => scenarioText(kpis, season, phase), [kpis, season, phase])
  return { season, phase, seasonObj, key, gkey, label, longLabel: scenarioText(kpis, season, phase, true) }
}

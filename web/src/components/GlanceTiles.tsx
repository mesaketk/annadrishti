import { useMemo } from 'react'
import { useStore } from '../lib/store'
import { globalKey, kpiBlock, nationalOutlook, scenarioKey } from '../lib/scenario'
import { useTrackerCounts } from '../lib/tracker'
import { plainCount } from '../lib/plain'
import type { District, PhaseId } from '../types'
import { Icon, Stat } from './ui'

/** "At a glance": six plain-language national tiles for the selected season and outlook. */
export default function GlanceTiles() {
  const { districts, kpis, season, phase } = useStore()
  const k = useMemo(() => {
    const keyOf = (d: District, ph: PhaseId) => scenarioKey(d, season, ph)
    const cur = kpiBlock(kpis, season, phase)
    const neu = kpiBlock(kpis, season, 'neutral')
    const gk = globalKey(districts, season, phase)
    const count = (ph: PhaseId, key: string) => kpis?.scenario_counts?.[key]?.high ?? districts.filter((d) => d.risk[keyOf(d, ph)]?.band === 'high').length
    const scored = districts.filter((d) => { const b = d.risk[keyOf(d, phase)]?.band; return b && b !== 'no_data' }).length
    if (cur && neu && cur.people_in_high_risk != null && neu.people_in_high_risk != null) {
      return {
        nAct: count(phase, gk), scored, pop: cur.people_in_high_risk, popNeutral: neu.people_in_high_risk,
        u5: cur.children_u5_in_high_risk ?? 0, shock: cur.national_expected_shock_pct ?? null, below: cur.districts_below_self_sufficiency ?? 0, known: cur.districts_with_balance ?? 0,
      }
    }
    let n = 0, pop = 0, u5 = 0, w = 0, ws = 0, below = 0, known = 0
    for (const d of districts) {
      const r = d.risk[keyOf(d, phase)]
      if (r?.band === 'high') { n++; pop += d.population_2026 ?? 0; u5 += d.children_u5_est ?? 0 }
      const s = r?.expected_yield_shock_pct, p = d.crops?.foodgrain_prod_t
      if (s != null && p != null) { w += p; ws += p * s }
      const ss = d.food_balance?.self_sufficiency
      if (ss != null) { known++; if (ss < 1) below++ }
    }
    return { nAct: n, scored, pop, popNeutral: pop, u5, shock: w ? ws / w : null, below, known }
  }, [districts, kpis, season, phase])

  const cp = kpis?.central_pool
  const track = useTrackerCounts()
  const setTrackerOpen = useStore((s) => s.setTrackerOpen)
  // Addendum I: hidden when the pipeline has not produced the field yet
  const so = nationalOutlook(kpis, season, phase)
  const rain = so?.rain_anom_pct
  const soLead = so?.plain ? so.plain.split(':')[0].trim().replace(/^./, (c) => c.toLowerCase()) : ''
  const shock = k.shock
  const shockTxt = shock == null ? '–' : `${Math.abs(shock) < 0.5 ? 'about the same' : `${Math.abs(shock).toFixed(1)} %`}`
  const worse = k.pop > k.popNeutral
  const tiles = (
    <>
      <Stat dense icon={<Icon name="groups" size={20} />} tone="act" label="People in Act-now districts" value={plainCount(k.pop)} unit="people" sub={phase === 'neutral' ? 'in a normal year' : `${plainCount(k.popNeutral)} in a normal year`} className={worse ? '' : ''} />
      <Stat dense icon={<Icon name="warning" size={20} />} tone="act" label="Districts: Act now" value={String(k.nAct)} unit="districts" sub={`out of ${k.scored} with an estimate`} />
      <Stat dense icon={<Icon name="child_care" size={20} />} tone="act" label="Children under 5 living there" value={plainCount(k.u5)} unit="children" />
      <Stat dense icon={<Icon name="grass" size={20} />} tone={shock != null && shock < -3 ? 'watch' : undefined} label="Foodgrain harvest vs usual" value={shockTxt} unit={shock == null || Math.abs(shock) < 0.5 ? '' : shock < 0 ? 'lower' : 'higher'} sub="expected, all India" />
      <Stat dense icon={<Icon name="inventory_2" size={20} />} tone="low" label="Central pool grain stock (FCI, national)" value={cp ? (Math.round(cp.total_lmt * 10) / 10).toString() : '–'} unit="lakh tonnes" sub={cp ? `not district stock · ${Math.round(cp.months_of_offtake)} months of ration supply` : 'not district stock'} />
      {rain != null && (
        <Stat dense icon={<Icon name="cloud" size={20} />} tone={rain <= -10 ? 'act' : rain <= -4 ? 'watch' : undefined} label="Upcoming season rain"
          value={Math.abs(rain) < 2 ? 'near normal' : `about ${Math.abs(rain).toFixed(0)} %`} unit={Math.abs(rain) < 2 ? '' : rain < 0 ? 'below normal' : 'above normal'}
          sub={[soLead, so?.rain_window].filter(Boolean).join(' · ') || undefined} />
      )}
      <Stat dense icon={<Icon name="restaurant" size={20} />} tone={k.below > k.known / 2 ? 'watch' : undefined} label="Districts growing less than they eat" value={String(k.below)} unit="districts" sub={`out of ${k.known} with data`} />
      <button type="button" onClick={() => setTrackerOpen(true)} className="md-state rounded-m3-md text-left [&>*]:h-full" aria-label={`Actions tracked: ${track.total}, ${track.done} done. Open the action tracker`}>
        <Stat dense icon={<Icon name="checklist" size={20} />} label="Actions tracked" value={String(track.total)} unit={`· ${track.done} done`} sub={track.total ? 'open the tracker' : 'none yet · add from a district'} />
      </button>
    </>
  )
  return (
    <section aria-label="At a glance" className="shrink-0 border-b border-outline-variant bg-surface px-3 py-3">
      <h2 className="mb-2 md-title-small">At a glance</h2>
      <div className="hide-scrollbar flex snap-x gap-2 overflow-x-auto xl:grid xl:grid-cols-4 xl:overflow-visible 2xl:grid-cols-8 [&>*]:min-w-[200px] [&>*]:flex-1 [&>*]:snap-start">{tiles}</div>
    </section>
  )
}

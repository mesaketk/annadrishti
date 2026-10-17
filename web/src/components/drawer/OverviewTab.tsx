import { groundwaterOf } from '../../lib/extra'
import { useStore } from '../../lib/store'
import type { District, Risk } from '../../types'
import { bigNum, harvestWords, imputedNote, monthName, NB, ndviTone, ndviWords, rainTone, rainWords, seasonName } from './copy'
import { Icon, type IconName } from '../ui'
import { Card, EstimatedTag, Stat, cx } from './ui'

const DOT = { good: 'bg-low-fill', ok: 'bg-outline-variant', bad: 'bg-act-fill' } as const

function Signal({ label, value, tone, note, src }: { label: string; value: string; tone: 'good' | 'ok' | 'bad'; note?: string | null; src?: string }) {
  return (
    <li className="flex items-start gap-3 py-2.5">
      <i aria-hidden className={cx('mt-2 h-2.5 w-2.5 shrink-0 rounded-full shadow-[inset_0_0_0_1px_rgb(0_0_0/0.28)]', DOT[tone])} />
      <div className="min-w-0 md-body text-on-surface">
        <span className="text-muted">{label}: </span><b className="font-medium">{value}</b>
        <EstimatedTag note={note ?? null} />
        {src && <span className="md-body-small text-muted"> ({src})</span>}
      </div>
    </li>
  )
}

function Fact({ icon, children }: { icon: IconName; children: React.ReactNode }) {
  return <li className="flex items-start gap-3"><span aria-hidden className="mt-0.5 flex text-primary"><Icon name={icon} size={20} /></span><span>{children}</span></li>
}

export default function OverviewTab({ d, r, scenarioKey, seasonId, seasonLabel, outlook }: { d: District; r: Risk | null; scenarioKey: string; seasonId: string | null; seasonLabel: string | null; outlook: string }) {
  const kpis = useStore((s) => s.kpis)
  const live = d.climate?.live
  const hw = harvestWords(r?.expected_yield_shock_pct)
  const pool = kpis?.central_pool
  const enso = kpis?.outlook?.enso ?? (kpis?.enso as unknown as { state?: string; nino34?: number; source?: string; p_by_season?: Record<string, { elnino?: number }> } | undefined)
  const pEl = seasonId ? (enso as { p_by_season?: Record<string, { elnino?: number }> } | undefined)?.p_by_season?.[seasonId]?.elnino : undefined
  const imputedRisk = (r as unknown as { imputed?: boolean } | null)?.imputed ? 'Estimated from neighbouring districts' : null
  const gw = groundwaterOf(d)
  const top = (d.crops?.top ?? []).slice(0, 3)
  const ss = d.food_balance?.self_sufficiency
  const seasonShort = seasonName(seasonId, d.main_season)

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <Stat icon="groups" label="People" value={d.population_2026 != null ? `${bigNum(d.population_2026)} people` : 'Not known'} sub="estimated for 2026" note={imputedNote(d, 'population_2026')} />
        <Stat icon="child_care" label="Children under 5" value={d.children_u5_est != null ? `${bigNum(d.children_u5_est)} children` : 'Not known'} sub="who need nutrition support first" note={imputedNote(d, 'children_u5_est', 'population_2026')} />
        <Stat icon="grass" label="Expected harvest" value={hw.text.charAt(0).toUpperCase() + hw.text.slice(1)} tone={hw.dir === 'down' && (r?.expected_yield_shock_pct ?? 0) <= -5 ? 'bad' : undefined}
          sub={r?.expected_yield_shock_pct != null ? `Foodgrain${seasonShort ? `, ${seasonShort}` : ''}, ${outlook}` : undefined} note={imputedRisk ?? imputedNote(d, `risk.${scenarioKey}`)} />
        <Stat icon="inventory_2" label="Grain in store" value={pool ? `${Math.round(pool.months_of_offtake)} months of grain in central stock` : 'Not known'}
          sub={<>{pool ? `Government stock for all India, ${monthName(pool.date.slice(0, 7), true)}. ` : ''}{d.food_balance?.pds_dependency != null ? `Ration shops supply about ${Math.round(d.food_balance.pds_dependency * 100)}${NB}% of this district's grain need.` : ''}</>}
          note={imputedNote(d, 'food_balance.pds_dependency')} />
      </div>

      <Card title="Right now">
        {live ? (
          <>
            <ul className="divide-y divide-outline-variant">
              {live.ndvi_anom != null && <Signal label="Vegetation this month" value={ndviWords(live.ndvi_anom)} tone={ndviTone(live.ndvi_anom)} note={imputedNote(d, 'climate.live.ndvi_anom', 'climate.live')} src="satellite greenness" />}
              {live.chirps_30d_anom_pct != null && <Signal label="Rain last 30 days" value={rainWords(live.chirps_30d_anom_pct)} tone={rainTone(live.chirps_30d_anom_pct)} note={imputedNote(d, 'climate.live.chirps_30d_anom_pct', 'climate.live')} />}
              {live.wn_10d_rain_mm != null && <Signal label="Next 10 days" value={`${live.wn_10d_rain_mm < 0.5 ? 'almost no' : `${live.wn_10d_rain_mm.toFixed(0)}${NB}mm`} rain expected`} tone={live.wn_10d_rain_mm < 5 ? 'ok' : 'good'} note={imputedNote(d, 'climate.live.wn_10d_rain_mm', 'climate.live')} src="Google WeatherNext" />}
            </ul>
            {live.as_of && <p className="mt-2 md-body-small text-muted">Updated {live.as_of}. Green dot: helpful, red dot: worrying, grey: neutral.</p>}
          </>
        ) : <p className="md-body text-muted">Live satellite and weather readings are not available for this district yet.</p>}
      </Card>

      {enso?.state && (
        <Card title="Weather outlook">
          <p className="md-body text-on-surface">
            {/el ni/i.test(enso.state) ? 'El Niño (a warm patch in the Pacific Ocean that usually weakens Indian rain) is active.' : `The Pacific Ocean is in a ${enso.state} phase.`}
            {pEl != null && seasonLabel && <> Chance it is still active for {seasonLabel}: {pEl >= 0.95 ? 'almost certain' : `about ${Math.round(pEl * 10)} in 10`}.</>}
          </p>
          {enso.source && <p className="mt-2 md-body-small text-muted">Source: {enso.source}</p>}
        </Card>
      )}

      <Card title="Good to know about farming here">
        <ul className="space-y-3 md-body text-on-surface">
          {top.length > 0 && <Fact icon="eco">Main crops: {top.map((c) => `${c.crop} (${Math.round(c.share * 100)}${NB}%)`).join(', ')}.</Fact>}
          {d.crops?.rainfed_share != null && <Fact icon="rainy">About {Math.round(d.crops.rainfed_share * 100)}{NB}% of farmland depends on rain alone.</Fact>}
          {gw?.depth != null && <Fact icon="water_drop">Water table about {Math.round(gw.depth)} m down{gw.decline != null && gw.decline > 0.05 ? `, falling about ${gw.decline.toFixed(1)} m a year` : ''}{gw.stress != null && gw.stress > 0.66 ? ' — under stress' : ''}.</Fact>}
          {ss != null && <Fact icon="restaurant">{ss >= 1 ? 'The district grows more grain than its people need.' : `The district grows about ${Math.round(ss * 100)}${NB}% of the grain its people need.`}</Fact>}
        </ul>
      </Card>
    </div>
  )
}

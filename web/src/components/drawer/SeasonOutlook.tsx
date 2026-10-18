import { phaseLabel } from '../../lib/scenario'
import { useStore } from '../../lib/store'
import type { District, PhaseId } from '../../types'
import { Icon, type IconName } from '../ui'
import { NB } from './copy'
import { isRabiId, outlookOf, plainOutlook } from './outlook'
import { Card, Pill } from './ui'

function Row({ icon, label, value, note }: { icon: IconName; label: string; value: string; note?: string }) {
  return (
    <li className="flex items-start gap-3 py-2.5">
      <span aria-hidden className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-secondary-container text-on-secondary-container"><Icon name={icon} size={20} /></span>
      <div className="min-w-0 md-body text-on-surface">
        <div className="md-body-small text-muted">{label}</div>
        <div className="font-medium">{value}</div>
        {note && <div className="md-body-small text-muted">{note}</div>}
      </div>
    </li>
  )
}

const sgn = (v: number, unit: string, digits = 0) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(digits)}${unit}`
const rainText = (v: number) => (Math.abs(v) < 3 ? 'close to normal' : `about ${Math.round(Math.abs(v))}${NB}% ${v < 0 ? 'below' : 'above'} normal`)
const heatText = (v: number) => (Math.abs(v) < 0.2 ? 'close to normal' : `about ${Math.abs(v).toFixed(1)}${NB}°C ${v > 0 ? 'hotter' : 'cooler'} than normal`)

/** Officer Overview: seasonal outlook for the selected season and phase, from district.season_outlook (Addendum I). */
export default function SeasonOutlookCard({ d, seasonId, seasonLabel, phase }: { d: District; seasonId: string | null; seasonLabel: string | null; phase: PhaseId }) {
  const kpis = useStore((s) => s.kpis)
  const o = outlookOf(d, seasonId, phase)
  const rabi = isRabiId(seasonId) || (!seasonId && d.main_season === 'OND')
  const sentence = plainOutlook('en', d, kpis, seasonId, phase)
  const rows: { icon: IconName; label: string; value: string; note?: string }[] = []
  if (o) {
    if (o.rain_anom_pct != null) rows.push({ icon: 'rainy', label: `Expected rain, ${o.rain_window ?? (rabi ? 'Oct–Dec' : 'Jun–Sep')}`, value: rainText(o.rain_anom_pct) })
    if (o.p_deficit_gt10 != null) rows.push({ icon: 'warning', label: 'Chance of a serious rain deficit (more than 10 % short)', value: `${Math.round(o.p_deficit_gt10 * 100)}${NB}%`, note: `about ${Math.round(o.p_deficit_gt10 * 10)} in 10` })
    if (o.tmax_anom_c != null) rows.push({ icon: 'thermostat', label: `Expected heat, ${o.heat_window ?? (rabi ? 'Feb–Mar' : 'Jun–Sep')}`, value: heatText(o.tmax_anom_c) })
    if (!rabi && o.onset_delay_days != null) rows.push({ icon: 'water_drop', label: 'Monsoon onset', value: o.onset_delay_days >= 2 ? `about ${Math.round(o.onset_delay_days)} days late` : 'on time' })
    if (!rabi && o.timesfm_rain_anom_pct != null) {
      rows.push({
        icon: 'auto_awesome', label: 'Google TimesFM view, national signal', value: `monsoon rain ${sgn(o.timesfm_rain_anom_pct, '%', 1)} vs normal`,
        note: o.timesfm_p10 != null && o.timesfm_p90 != null ? `likely range ${sgn(o.timesfm_p10, '%')} to ${sgn(o.timesfm_p90, '%')}. Country-level, not specific to this district.` : 'Country-level, not specific to this district.',
      })
    }
  }
  return (
    <Card title={`Season outlook${seasonLabel ? ` · ${seasonLabel}` : ''}`} aside={<Pill tone="info" className="whitespace-nowrap">{phaseLabel(phase)}</Pill>}>
      <p className="-mt-1 mb-2 md-body text-on-surface-variant" data-testid="outlook-sentence">{sentence}</p>
      {rows.length > 0
        ? <ul className="divide-y divide-outline-variant" data-testid="season-outlook">{rows.map((r) => <Row key={r.label} {...r} />)}</ul>
        : <p className="md-body-small text-muted">Detailed rain and heat figures for this season are not available for this district yet.</p>}
    </Card>
  )
}

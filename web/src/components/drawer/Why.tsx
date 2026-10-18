import { districtModelsOf } from '../../lib/models'
import { bandOf, thresholdsOf } from '../../lib/scales'
import { useStore } from '../../lib/store'
import type { District, Lang, PhaseId, Risk } from '../../types'
import { driversOf, NB } from './copy'
import type { DriverView } from './copy'
import { driverLocal, t } from './i18n'
import { localWindow } from './i18n.extra'
import { outlookOf, plainOutlook } from './outlook'
import { Icon, type IconName } from '../ui'
import { Accordion, Card, IconSentence, TrafficLight } from './ui'
import { C } from './theme'

/** Climate groups only: what the farmer Why tab may show (no nutrition, PDS, price or groundwater drivers). */
const CLIMATE_GROUPS: DriverView['group'][] = ['rain', 'heat']

export const climateDrivers = (d: District, r: Risk | null) => driversOf(d, r).filter((x) => CLIMATE_GROUPS.includes(x.group))

/** Top-N drivers as icon sentences. `lang` switches to local-language templates where available (farmer view). `climateOnly` keeps rain and heat drivers. */
export function TopDrivers({ d, r, n = 3, lang, climateOnly = false }: { d: District; r: Risk | null; n?: number; lang?: Lang; climateOnly?: boolean }) {
  const list = (climateOnly ? climateDrivers(d, r) : driversOf(d, r)).slice(0, n)
  if (r?.band === 'no_data' || list.length === 0) return <p className="md-body text-muted">{lang ? t(lang, 'why.none') : 'No estimate available for this district yet.'}</p>
  return (
    <ul className="space-y-3.5">
      {list.map((x) => <IconSentence key={x.name} icon={x.icon}>{(lang && driverLocal(lang, x.key, x.params)) || x.sentence}</IconSentence>)}
    </ul>
  )
}

/** Plain outlook sentence for the selected season and phase (farmer view). */
export function OutlookSentence({ d, lang, season, phase }: { d: District; lang: Lang; season: string | null; phase: PhaseId }) {
  const kpis = useStore((s) => s.kpis)
  return (
    <section className="flex items-start gap-3 rounded-m3-lg bg-secondary-container p-4 text-on-secondary-container" aria-label={t(lang, 'why.outlook')} data-testid="outlook-sentence">
      <span aria-hidden className="mt-0.5 flex"><Icon name="rainy" size={24} /></span>
      <div>
        <div className="md-label-large opacity-80">{t(lang, 'why.outlook')}</div>
        <p className="md-title-medium">{plainOutlook(lang, d, kpis, season, phase)}</p>
      </div>
    </section>
  )
}

/** "Rain and heat this season": rain vs normal, chance of a serious deficit, heat, monsoon onset. Hidden until season_outlook exists. */
export function RainHeatCard({ d, lang, season, phase }: { d: District; lang: Lang; season: string | null; phase: PhaseId }) {
  const o = outlookOf(d, season, phase)
  if (!o) return null
  const rabi = !!season && /^rabi/i.test(season)
  const win = (w: string | null | undefined, fb: string) => localWindow(lang, w || fb)
  const rows: { icon: IconName; text: string }[] = []
  if (o.rain_anom_pct != null) {
    const v = o.rain_anom_pct, w = win(o.rain_window, rabi ? 'Oct–Dec' : 'Jun–Sep')
    rows.push({ icon: 'rainy', text: t(lang, Math.abs(v) < 3 ? 'rh.rain.norm' : v < 0 ? 'rh.rain.less' : 'rh.rain.more', { n: Math.round(Math.abs(v)), win: w }) })
  }
  if (o.p_deficit_gt10 != null) {
    const k = Math.round(o.p_deficit_gt10 * 10)
    rows.push({ icon: 'warning', text: k >= 1 ? t(lang, 'rh.deficit', { k }) : t(lang, 'rh.deficit.low') })
  }
  if (o.tmax_anom_c != null) {
    const v = o.tmax_anom_c, w = win(o.heat_window, rabi ? 'Feb–Mar' : 'Jun–Sep')
    rows.push({ icon: 'thermostat', text: t(lang, Math.abs(v) < 0.2 ? 'rh.heat.norm' : v > 0 ? 'rh.heat.hot' : 'rh.heat.cool', { n: Math.abs(v).toFixed(1), win: w }) })
  }
  if (!rabi && o.onset_delay_days != null) {
    rows.push({ icon: 'water_drop', text: o.onset_delay_days >= 2 ? t(lang, 'rh.onset.late', { n: Math.round(o.onset_delay_days) }) : t(lang, 'rh.onset.ok') })
  }
  if (!rows.length) return null
  return (
    <Card title={t(lang, 'rh.title')}>
      <ul className="space-y-3.5" data-testid="rain-heat">
        {rows.map((x) => <IconSentence key={x.icon + x.text} icon={x.icon}>{x.text}</IconSentence>)}
      </ul>
    </Card>
  )
}

/** Past El Niño years: one plain sentence (farmer Why tab). */
export function PastElNinoSentence({ d, lang }: { d: District; lang: Lang }) {
  const rain = d.climate?.elnino_mean_anomaly_pct, harvest = d.yield_sensitivity?.foodgrain_elnino_pct
  if (rain == null || harvest == null || rain >= 0 || harvest >= 0) return null
  return (
    <p className="flex items-start gap-3 rounded-m3-md bg-surface-container p-4 md-body text-on-surface">
      <span aria-hidden className="flex text-primary"><Icon name="history" /></span>
      <span>{t(lang, 'why.past', { rain: Math.round(Math.abs(rain)), yield: Math.round(Math.abs(harvest)) })}</span>
    </p>
  )
}

// ------------------------------------------------------------------ gauges
function Gauge({ title, hint, v, goodHigh = false }: { title: string; hint: string; v: number | null; goodHigh?: boolean }) {
  const rad = 24, circ = 2 * Math.PI * rad
  const x = v == null ? 0 : Math.max(0, Math.min(1, v))
  const bad = goodHigh ? 1 - x : x
  const col = v == null ? C.nodata : bad > 0.66 ? C.act : bad > 0.4 ? C.watch : C.low
  const word = v == null ? 'unknown' : x > 0.66 ? 'high' : x > 0.4 ? 'medium' : 'low'
  return (
    <div className="flex flex-1 flex-col items-center text-center">
      <svg width="64" height="64" viewBox="0 0 64 64" role="img" aria-label={`${title}: ${word}`}>
        <circle cx="32" cy="32" r={rad} fill="none" stroke={C.line} strokeWidth="7" />
        <circle cx="32" cy="32" r={rad} fill="none" stroke={col} strokeWidth="7" strokeLinecap="round" strokeDasharray={`${circ * x} ${circ}`} transform="rotate(-90 32 32)" />
        <text x="32" y="36" textAnchor="middle" fontSize="12" fontWeight="700" fill={C.ink}>{v == null ? '–' : Math.round(x * 100)}</text>
      </svg>
      <div className="mt-1 md-label-large text-on-surface">{title}</div>
      <div className="md-label-medium capitalize text-muted">{word}</div>
      <div className="mt-0.5 md-body-small leading-tight text-muted">{hint}</div>
    </div>
  )
}
export function Gauges({ r }: { r: Risk | null }) {
  if (!r || r.exposure == null) return null
  return (
    <div className="flex gap-2">
      <Gauge title="Weather pressure" hint="how hard the coming weather could hit" v={r.exposure} />
      <Gauge title="How easily hurt" hint="how easily crops and families suffer" v={r.sensitivity} />
      <Gauge title="Ability to cope" hint="resources to absorb and recover" v={r.capacity} goodHigh />
    </div>
  )
}

// ------------------------------------------------------------------ model agreement in words
export function ModelAgreementPlain({ d, scenarioKey }: { d: District; scenarioKey: string }) {
  const kpis = useStore((s) => s.kpis)
  const m = districtModelsOf(d, scenarioKey, kpis)
  const s = m?.scenario
  const tf = m?.timesfm
  if (!s && !tf) return null
  const a = s?.analog ?? null, l = s?.lgbm ?? null, e = s?.ensemble ?? null
  const dir = (v: number) => (v < 0 ? 'lower' : 'higher')
  const r0 = (v: number) => Math.round(Math.abs(v))
  let text = ''
  let tone: 'agree' | 'mixed' | 'differ' | 'single' = 'single'
  if (a != null && l != null) {
    const lo = Math.min(a, l), hi = Math.max(a, l), gap = hi - lo
    const mid = e ?? (a + l) / 2
    const range = Math.sign(lo) === Math.sign(hi) || Math.min(Math.abs(lo), Math.abs(hi)) < 0.5
      ? `${r0(lo) === r0(hi) ? r0(lo) : `${Math.min(r0(lo), r0(hi))}–${Math.max(r0(lo), r0(hi))}`}`
      : `${r0(lo)} lower to ${r0(hi)} higher`
    if (gap <= 3) { tone = 'agree'; text = `Two methods agree: ${r0(mid)}${NB}% ${dir(mid)} harvest (range ${range}${NB}%).` }
    else if (gap <= 8) { tone = 'mixed'; text = `Two methods roughly agree: about ${r0(mid)}${NB}% ${dir(mid)} harvest (range ${range}${NB}%).` }
    else { tone = 'differ'; text = `The two methods disagree: looking at past El Niño years suggests ${r0(a)}${NB}% ${dir(a)}, a computer model trained on past years suggests ${r0(l)}${NB}% ${dir(l)}. We use a blend, about ${r0(mid)}${NB}% ${dir(mid)}.` }
  } else if (e != null || a != null || l != null) {
    const v = (e ?? a ?? l) as number
    text = `Only one method could be run here: about ${r0(v)}${NB}% ${dir(v)} harvest.`
  }
  const lo = Math.min(a ?? e ?? 0, l ?? e ?? 0), hi = Math.max(a ?? e ?? 0, l ?? e ?? 0)
  const ext = Math.max(10, Math.abs(lo), Math.abs(hi)) * 1.15
  const pos = (v: number) => 50 + (v / ext) * 50
  return (
    <div>
      <h4 className="mb-2 md-title-small text-on-surface">How sure are we about the harvest estimate?</h4>
      {text && <p className="md-body text-on-surface">{text}</p>}
      {text && (
        <div className="relative mt-3 h-2 rounded-full bg-surface-container-highest" role="img" aria-label={text}>
          <div className="absolute inset-y-0 w-px bg-muted" style={{ left: '50%' }} />
          <div className={`absolute inset-y-0 rounded-full ${tone === 'differ' ? 'bg-watch-fill' : 'bg-primary'}`} style={{ left: `${pos(lo)}%`, width: `${Math.max(1.5, pos(hi) - pos(lo))}%` }} />
          {e != null && <i className="absolute -top-1 h-4 w-1.5 -translate-x-1/2 rounded bg-on-surface" style={{ left: `${pos(e)}%` }} />}
        </div>
      )}
      {text && <div className="mt-1 flex justify-between md-body-small text-muted"><span>lower harvest</span><span>normal</span><span>higher harvest</span></div>}
      {tf && tf.anom != null && (
        <p className="mt-3 md-body-medium text-muted">
          National forecast for next monsoon rain: about {r0(tf.anom)}{NB}% {tf.anom < 0 ? 'below' : 'above'} normal{tf.p10 != null && tf.p90 != null ? ` (likely range ${Math.round(tf.p10)}${NB}% to ${tf.p90 > 0 ? '+' : ''}${Math.round(tf.p90)}${NB}%)` : ''}. This is a country-level signal, not specific to this district.
        </p>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ hindcast in words
const KHARIF_YEARS = ['2009', '2014', '2015', '2023']
export function HindcastPlain({ d, rabi }: { d: District; rabi: boolean }) {
  const kpis = useStore((s) => s.kpis)
  const thr = thresholdsOf(kpis)
  const block = rabi && d.hindcast_rabi && Object.keys(d.hindcast_rabi).length ? d.hindcast_rabi : d.hindcast
  const years = block === d.hindcast_rabi ? Object.keys(block ?? {}).sort() : KHARIF_YEARS
  const rows = years.map((y) => {
    const h = block?.[y]
    if (!h) return null
    const harvest = h.actual_foodgrain_yield_dev_pct ?? (h as unknown as { actual_rabi_yield_dev_pct?: number | null }).actual_rabi_yield_dev_pct ?? null
    const band = bandOf(h.predicted_score, thr)
    return band || harvest != null ? { y, band, harvest } : null
  }).filter((x): x is { y: string; band: ReturnType<typeof bandOf>; harvest: number | null } => x != null)
  if (!rows.length) return null
  let shocks = 0, hits = 0
  for (const r of rows) if (r.harvest != null && r.harvest <= -5) { shocks++; if (r.band && r.band !== 'low') hits++ }
  return (
    <div>
      <h4 className="mb-2 md-title-small text-on-surface">Would this tool have warned in past bad years?</h4>
      <ul className="space-y-2">
        {rows.map((r) => {
          return (
            <li key={r.y} className="md-body text-on-surface">
              <span className="font-medium">In {r.y}</span> this tool would have said <TrafficLight band={r.band} size="sm" className="align-middle" />
              {r.harvest != null && <>. The harvest {r.harvest < 0 ? 'fell' : 'rose'} {Math.abs(Math.round(r.harvest))}{NB}%.</>}
            </li>
          )
        })}
      </ul>
      {shocks > 0 && <p className="mt-2 md-body-medium text-muted">It flagged Watch or Act now in {hits} of {shocks} {shocks === 1 ? 'year' : 'years'} when the harvest fell 5{NB}% or more below trend. Harvest change is against the usual trend for that year.</p>}
    </div>
  )
}

// ------------------------------------------------------------------ full breakdown accordion
export function FullBreakdown({ d, r, scenarioKey, rabi }: { d: District; r: Risk | null; scenarioKey: string; rabi: boolean }) {
  const all: DriverView[] = driversOf(d, r)
  return (
    <Accordion title="Full breakdown">
      <div>
        <h4 className="mb-3 md-title-small text-on-surface">All the pressures, biggest first</h4>
        {all.length === 0 ? <p className="md-body text-muted">No breakdown available.</p> : (
          <ul className="space-y-3">{all.map((x) => <IconSentence key={x.name} icon={x.icon} weight={x.weight}>{x.sentence}</IconSentence>)}</ul>
        )}
      </div>
      <Gauges r={r} />
      <ModelAgreementPlain d={d} scenarioKey={scenarioKey} />
      <HindcastPlain d={d} rabi={rabi} />
    </Accordion>
  )
}

import type { ReactNode } from 'react'
import { useId, useMemo } from 'react'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Customized, LabelList, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { marketsOf, poshanOf } from '../../lib/extra'
import { bandOf, thresholdsOf } from '../../lib/scales'
import { useStore } from '../../lib/store'
import { useScenario } from '../../lib/useScenario'
import type { District, Lang, Timeseries } from '../../types'
import { AXIS, C } from './theme'
import { isEl, lightOf, mean, monthName, NB, seasonName, seasonWhen } from './copy'
import { poshanForecast, phaseShort, rainForecast, rangeOf, yieldForecast } from './forecast'
import { t } from './i18n'
import { localWindow } from './i18n.extra'
import { isRabiId } from './outlook'
import { Icon } from '../ui'
import { Card } from './ui'

type Rec = Record<string, unknown>
const isRec = (x: unknown): x is Rec => typeof x === 'object' && x !== null && !Array.isArray(x)
const numOrNull = (x: unknown): number | null => (typeof x === 'number' && Number.isFinite(x) ? x : null)

export function ChartCard({ title, caption, source, children, right }: { title: string; caption?: ReactNode; source?: string; children: ReactNode; right?: ReactNode }) {
  return (
    <Card title={title} aside={right}>
      {caption && <p className="-mt-1 mb-3 md-body-medium text-on-surface-variant">{caption}</p>}
      {children}
      {source && <p className="mt-2 md-body-small text-muted">Source: {source}</p>}
    </Card>
  )
}

interface TipProps { active?: boolean; payload?: { payload: Rec }[]; render: (p: Rec) => ReactNode }
function Tip({ active, payload, render }: TipProps) {
  if (!active || !payload?.length) return null
  return <div className="rounded-m3-xs bg-inverse-surface px-2 py-1 md-body-small text-inverse-on-surface">{render(payload[0].payload)}</div>
}
const signed = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(Math.round(v))}${NB}%`

// ------------------------------------------------------------------ year highlight note
export function useYearNote(d: District, ts: Timeseries | null, year: number | undefined): string | null {
  const kpis = useStore((s) => s.kpis)
  return useMemo(() => {
    if (year == null) return null
    const y = String(year)
    const h = d.hindcast?.[y] ?? d.hindcast_rabi?.[y] ?? null
    const rain = h?.rain_anomaly_pct ?? numOrNull((ts as unknown as Rec | null)?.jjas_anomaly_pct && ((ts as unknown as Rec).jjas_anomaly_pct as Rec)[y]) ?? d.climate?.jjas_anomaly_pct?.[y] ?? null
    if (h) {
      const harvest = h.actual_foodgrain_yield_dev_pct ?? numOrNull((h as unknown as Rec).actual_rabi_yield_dev_pct)
      const band = bandOf(h.predicted_score, thresholdsOf(kpis))
      const parts = [rain != null ? `rain ${signed(rain)}` : null, harvest != null ? `harvest ${signed(harvest)} vs trend` : null].filter(Boolean).join(', ')
      const said = band ? ` — the tool would have said ${lightOf(band).label}` : ''
      return `${y}: ${parts}${said}`
    }
    const yy = ts?.yield.foodgrain_t_ha?.[y]
    const parts = [rain != null ? `rain ${signed(rain)}` : null, yy != null ? `harvest ${yy.toFixed(2)} tonnes per hectare` : null].filter(Boolean).join(', ')
    return parts ? `${y}: ${parts} (observed)` : null
  }, [d, ts, year, kpis])
}


// ------------------------------------------------------------------ forecast legend + helpers
type SwKind = 'line' | 'fc' | 'dash' | 'hatch' | 'whisker'
function Swatch({ k }: { k: SwKind }) {
  return (
    <svg width="22" height="12" viewBox="0 0 22 12" aria-hidden className="shrink-0">
      {k === 'line' && <line x1="1" y1="6" x2="21" y2="6" stroke={C.accent} strokeWidth="2.5" />}
      {k === 'fc' && <><rect x="1" y="1" width="20" height="10" fill={C.band} opacity="0.9" /><line x1="1" y1="6" x2="21" y2="6" stroke={C.accent} strokeWidth="2" strokeDasharray="4 3" /><circle cx="17" cy="6" r="3" fill={C.bg} stroke={C.accent} strokeWidth="1.75" /></>}
      {k === 'dash' && <><line x1="1" y1="6" x2="21" y2="6" stroke={C.accent} strokeWidth="2" strokeDasharray="4 3" /><circle cx="17" cy="6" r="3" fill={C.bg} stroke={C.accent} strokeWidth="1.75" /></>}
      {k === 'hatch' && <><rect x="6" y="1" width="10" height="10" fill={C.band} stroke={C.accent} strokeWidth="1.25" /><path d="M6 8 L12 2 M6 12 L16 2 M10 12 L16 6" stroke={C.accent} strokeWidth="1" /></>}
      {k === 'whisker' && <g stroke={C.outline} strokeWidth="1.5"><line x1="11" y1="1" x2="11" y2="11" /><line x1="8" y1="1" x2="14" y2="1" /><line x1="8" y1="11" x2="14" y2="11" /></g>}
    </svg>
  )
}
function FcLegend({ items, dots = false }: { items: { k: SwKind; label: string }[]; dots?: boolean }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 md-label-medium text-muted">
      {items.map((it, i) => <span key={it.label} className="flex items-center gap-1.5">{dots && i > 0 && <span aria-hidden className="mr-0.5">·</span>}<Swatch k={it.k} />{it.label}</span>)}
    </div>
  )
}
const cap1 = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)
/** Tick years every 5 years plus the forecast year (skipping ones too close to it). */
const fcTicks = (years: number[], fy: number) => [...years.filter((y) => y % 5 === 0 && y <= fy - 4).map(String), String(fy)]

// ------------------------------------------------------------------ yield
export function YieldChart({ d, ts, year, lang }: { d: District; ts: Timeseries; year?: number; lang?: Lang }) {
  const farmer = lang != null
  const sc = useScenario()
  const status = sc.seasonObj?.status ?? null
  const { data, ymax, caption, fc, ticks, legend } = useMemo(() => {
    const ys = ts.yield.foodgrain_t_ha ?? {}
    const years = Object.keys(ys).filter((y) => +y >= 2000 && +y <= 2024).sort()
    const vals = years.map((y) => ys[y]).filter((v): v is number => v != null)
    const el = (y: string) => isEl(ts.oni_phase?.[y])
    const first = mean(years.slice(0, 5).map((y) => ys[y]).filter((v): v is number => v != null))
    const last = mean(years.slice(-5).map((y) => ys[y]).filter((v): v is number => v != null))
    const lastObs = [...years].reverse().find((y) => ys[y] != null)
    let fc = lastObs != null ? yieldForecast(d, sc.season, sc.phase, last) : null
    if (fc && fc.year <= +lastObs!) fc = null
    const ymax = Math.max(0.5, Math.ceil(Math.max(0.1, ...vals, fc?.hi ?? 0) * 1.08 * 2) / 2)
    const data: { year: string; y: number | null; enso: number | null; f?: number | null; band?: [number, number] | null; fc?: boolean }[] = years.map((y) => ({ year: y, y: ys[y], enso: el(y) ? ymax : null, ...(fc ? { f: y === lastObs ? ys[y] : null, band: y === lastObs ? [ys[y]!, ys[y]!] as [number, number] : null } : {}) }))
    if (fc) {
      for (let y = +lastObs! + 1; y < fc.year; y++) data.push({ year: String(y), y: null, enso: null, f: null, band: null })
      data.push({ year: String(fc.year), y: null, enso: null, f: fc.value, band: [fc.lo, fc.hi], fc: true })
    }
    let sens = d.yield_sensitivity?.foodgrain_elnino_pct ?? null
    if (sens == null) {
      const a = mean(years.filter(el).map((y) => ys[y]).filter((v): v is number => v != null)), b = mean(years.filter((y) => !el(y)).map((y) => ys[y]).filter((v): v is number => v != null))
      if (a != null && b != null && b > 0) sens = (a / b - 1) * 100
    }
    let caption: string
    if (farmer) caption = sens != null && sens < -1 ? t(lang!, 'trends.yield.cap.n', { n: Math.round(Math.abs(sens)) }) : t(lang!, 'trends.yield.cap')
    else {
      const trend = first != null && last != null ? `Grain harvested per hectare has ${last > first * 1.05 ? 'risen' : last < first * 0.95 ? 'fallen' : 'stayed roughly flat'} (about ${first.toFixed(1)} tonnes in the early 2000s, ${last.toFixed(1)} in the last five years).` : ''
      const e = sens != null ? ` In El Niño years (shaded) the harvest ran about ${Math.round(Math.abs(sens))}${NB}% ${sens < 0 ? 'below' : 'above'} its usual trend.` : ' El Niño years are shaded.'
      caption = trend + e
    }
    let legend = ''
    let ticks: string[] | undefined
    if (fc) {
      const n = Math.round(Math.abs(fc.shock)), rg = rangeOf(fc.loPct, fc.hiPct)
      const sname = seasonName(sc.season, d.main_season)
      if (farmer) {
        const L = lang!
        const when = sname ? t(L, status === 'upcoming' ? 'season.next' : 'season.this', { season: t(L, /rabi/i.test(sname) ? 'season.rabi' : 'season.kharif') }) : t(L, 'season.none')
        caption += ` ${t(L, n < 1 ? 'fc.yield.flat' : fc.shock < 0 ? 'fc.yield.below' : 'fc.yield.above', { when, n })}${rg ? ` (${t(L, 'fc.range', rg)})` : ''}.`
        legend = `${t(L, 'fc.observed')} · ${t(L, 'fc.expected')}${sname ? ` (${when})` : ''}`
      } else {
        const when = cap1(seasonWhen(sc.season, status, d.main_season))
        caption += ` ${when}: ${n < 1 ? 'close to a normal year' : `about ${n}${NB}% ${fc.shock < 0 ? 'below' : 'above'} a normal year`}${rg ? ` (range ${rg.a}–${rg.b}${NB}%)` : ''}.`
        legend = `Expected (${[sname, phaseShort(sc.phase)].filter(Boolean).join(', ')})`
      }
      ticks = fcTicks(years.map(Number), fc.year)
    }
    return { data, ymax, caption, fc, ticks, legend }
  }, [ts, d, farmer, lang, sc.season, sc.phase, status])
  const note = useYearNote(d, ts, year)
  if (data.length < 3) return null
  const rg = fc ? rangeOf(fc.loPct, fc.hiPct) : null
  return (
    <ChartCard title={farmer ? t(lang!, 'trends.yield.title') : 'Grain harvested per hectare, 2000–2024'} caption={caption} source={farmer ? undefined : 'crop statistics from the Ministry of Agriculture (area, production, yield); El Niño years from NOAA; expected harvest from the district risk model (last five-year mean × expected shock)'}
      right={<span className="flex items-center gap-1.5 md-label-medium text-muted"><i className="inline-block h-3 w-3 rounded-sm" style={{ background: C.elnino, border: `1px solid ${C.act}55` }} />El Niño</span>}>
      <div role="img" aria-label={note ?? `Line chart of grain yield per hectare by year, El Niño years shaded${fc ? `; expected ${fc.year}: ${fc.value.toFixed(2)} tonnes per hectare` : ''}`}>
        <ResponsiveContainer width="100%" height={farmer ? 190 : 170}>
          <ComposedChart data={data} margin={{ top: 18, right: 8, left: -14, bottom: 0 }} barCategoryGap={0}>
            <CartesianGrid stroke={C.line} vertical={false} />
            <XAxis dataKey="year" {...AXIS} {...(ticks ? { ticks, interval: 0 } : { interval: 4 })} />
            <YAxis {...AXIS} domain={[0, ymax]} tickCount={5} tickFormatter={(v: number) => v.toFixed(1)} width={40} />
            <Tooltip content={<Tip render={(p) => <><b>{String(p.year)}</b>{p.fc ? <span className="text-inverse-primary"> · expected</span> : null}{p.enso != null && <span className="text-inverse-primary"> · El Niño year</span>}<br />{p.fc ? <>{(p.f as number).toFixed(2)} tonnes per hectare<br />{`${Math.round(Math.abs(fc!.shock))}${NB}% ${fc!.shock < 0 ? 'below' : 'above'} a normal year${rg ? ` (range ${rg.a}–${rg.b}${NB}%)` : ''}`}</> : p.y == null ? 'No data' : `${(p.y as number).toFixed(2)} tonnes per hectare`}</>} />} />
            {fc && <Area type="linear" dataKey="band" stroke="none" fill={C.band} fillOpacity={0.85} connectNulls isAnimationActive={false} legendType="none" activeDot={false} />}
            <Bar dataKey="enso" fill={C.elnino} isAnimationActive={false} legendType="none" />
            <Line type="monotone" dataKey="y" stroke={C.accent} strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} connectNulls isAnimationActive={false} />
            {fc && <Line type="linear" dataKey="f" stroke={C.accent} strokeWidth={2} strokeDasharray="5 4" connectNulls isAnimationActive={false} activeDot={false}
              dot={(p: { cx?: number; cy?: number; index?: number; payload?: { fc?: boolean } }) => (p.payload?.fc && p.cx != null && p.cy != null ? <circle key={`fc-${p.index}`} cx={p.cx} cy={p.cy} r={5} fill={C.bg} stroke={C.accent} strokeWidth={2} /> : <g key={`fc-${p.index}`} />)} />}
            {year != null && <ReferenceLine x={String(year)} stroke={C.ink} strokeDasharray="4 3" label={{ value: String(year), position: 'top', fontSize: 11, fill: C.ink }} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {fc && <FcLegend dots items={farmer ? [{ k: 'line', label: legend.split(' · ')[0] }, { k: 'fc', label: legend.split(' · ').slice(1).join(' · ') }] : [{ k: 'line', label: 'Observed' }, { k: 'fc', label: legend }]} />}
    </ChartCard>
  )
}

// ------------------------------------------------------------------ rain
interface RainFcLayerProps { xAxisMap?: Record<string, { scale?: any }>; yAxisMap?: Record<string, { scale?: any }>; fy: string; v: number; tfm: { med: number; p10: number; p90: number } | null; uid: string } // eslint-disable-line @typescript-eslint/no-explicit-any
/** Hatched expected-rain bar plus the TimesFM p10-p90 whisker beside it, drawn from the chart's own scales. */
function RainFcLayer({ xAxisMap, yAxisMap, fy, v, tfm, uid }: RainFcLayerProps) {
  const xs = Object.values(xAxisMap ?? {})[0]?.scale, ysc = Object.values(yAxisMap ?? {})[0]?.scale
  if (!xs || !ysc) return null
  const bx: number = xs(fy)
  if (!Number.isFinite(bx)) return null
  const bw: number = typeof xs.bandwidth === 'function' ? xs.bandwidth() : 10
  const y0: number = ysc(0), yv: number = ysc(v)
  const barX = bx + bw * 0.1, barW = bw * (tfm ? 0.5 : 0.8), wx = bx + bw * 0.82
  return (
    <g pointerEvents="none">
      <defs><pattern id={uid} width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="4" height="4" fill={C.band} /><rect width="1.6" height="4" fill={C.accent} /></pattern></defs>
      <rect x={barX} y={Math.min(y0, yv)} width={barW} height={Math.max(1.5, Math.abs(yv - y0))} fill={`url(#${uid})`} stroke={C.accent} strokeWidth={1.25} />
      {tfm && <g stroke={C.outline} strokeWidth={1.25}>
        <line x1={wx} x2={wx} y1={ysc(tfm.p90)} y2={ysc(tfm.p10)} />
        <line x1={wx - 2.5} x2={wx + 2.5} y1={ysc(tfm.p90)} y2={ysc(tfm.p90)} />
        <line x1={wx - 2.5} x2={wx + 2.5} y1={ysc(tfm.p10)} y2={ysc(tfm.p10)} />
        <circle cx={wx} cy={ysc(tfm.med)} r={2.25} fill={C.outline} stroke="none" />
      </g>}
    </g>
  )
}

export function RainChart({ d, ts, year, lang }: { d: District; ts: Timeseries | null; year?: number; lang?: Lang }) {
  const farmer = lang != null
  const sc = useScenario()
  const uid = `rf${useId().replace(/[^a-zA-Z0-9]/g, '')}`
  const { data, caption, fc, ond, ticks, domain, yticks, legend } = useMemo(() => {
    const climate = (d.climate ?? null) as unknown as Rec | null
    const pick = (k: string): Record<string, number | null> | null => (isRec(climate?.[k]) ? (climate![k] as Record<string, number | null>) : isRec((ts as unknown as Rec | null)?.[k]) ? ((ts as unknown as Rec)[k] as Record<string, number | null>) : null)
    const rabi = isRabiId(sc.season) || (!sc.season && d.main_season === 'OND')
    const ondSeries = rabi ? pick('ond_anomaly_pct') : null
    const ond = !!ondSeries
    const a = ondSeries ?? pick('jjas_anomaly_pct') ?? {}
    const years = Object.keys(a).filter((y) => a[y] != null && +y >= 2000).sort()
    const rows: { year: string; v: number | null; el: boolean; fc?: boolean }[] = years.map((y) => ({ year: y, v: a[y] as number, el: isEl(ts?.oni_phase?.[y]) }))
    const obs = rows.filter((x) => x.v != null) as { year: string; v: number; el: boolean }[]
    const below = obs.filter((x) => x.v < 0).length
    const elAvg = ond ? mean(obs.filter((x) => x.el).map((x) => x.v)) : d.climate?.elnino_mean_anomaly_pct ?? mean(obs.filter((x) => x.el).map((x) => x.v))
    let caption: string
    if (farmer) caption = !ond && elAvg != null && elAvg < -1 ? t(lang!, 'trends.rain.cap.n', { n: Math.round(Math.abs(elAvg)) }) : t(lang!, 'trends.rain.cap')
    else {
      caption = `${ond ? 'Winter-season rain (October–December)' : 'Monsoon rain (June–September)'} was below normal in ${below} of the last ${obs.length} years.` + (elAvg != null ? ` In El Niño years it averaged ${Math.round(Math.abs(elAvg))}${NB}% ${elAvg < 0 ? 'below' : 'above'} normal${!ond && d.climate?.jjas_normal_mm ? ` (normal is about ${Math.round(d.climate.jjas_normal_mm)} mm)` : ''}.` : '')
    }
    const lastObs = years.length ? +years[years.length - 1] : null
    let fc = lastObs != null && (ond || !rabi) ? rainForecast(d, sc.season, sc.phase) : null
    if (fc && fc.year <= lastObs!) fc = null
    let domain: [number, number] | undefined, yticks: number[] | undefined, ticks: string[] | undefined, legend = ''
    if (fc) {
      for (let y = lastObs! + 1; y < fc.year; y++) rows.push({ year: String(y), v: null, el: false })
      rows.push({ year: String(fc.year), v: null, el: false, fc: true })
      const lo = Math.min(0, ...obs.map((x) => x.v), fc.v, fc.tfm?.p10 ?? 0), hi = Math.max(0, ...obs.map((x) => x.v), fc.v, fc.tfm?.p90 ?? 0)
      const step = [10, 20, 25, 50, 100, 200].find((st) => (hi - lo) / st <= 6) ?? 250
      domain = [Math.floor(lo / step) * step, Math.ceil(hi / step) * step]
      yticks = Array.from({ length: (domain[1] - domain[0]) / step + 1 }, (_, i) => domain![0] + i * step)
      ticks = fcTicks(years.map(Number), fc.year)
      const n = Math.round(Math.abs(fc.v))
      if (farmer) {
        const L = lang!
        const when = `${localWindow(L, fc.window)} ${fc.year}`
        caption += ` ${t(L, n < 1 ? 'fc.rain.flat' : fc.v < 0 ? 'fc.rain.below' : 'fc.rain.above', { when, n })}.`
        legend = `${t(L, 'fc.expected')}: ${when}`
      } else {
        caption += ` Outlook for ${fc.window} ${fc.year} (${phaseShort(sc.phase)}): ${n < 1 ? 'close to normal rain' : `about ${n}${NB}% ${fc.v < 0 ? 'less' : 'more'} rain than normal`}.`
          + (fc.tfm ? ` TimesFM's central estimate is ${signed(fc.tfm.med)}, with a likely range of ${signed(fc.tfm.p10)} to ${signed(fc.tfm.p90)}.` : '')
        legend = `${fc.window} ${fc.year} expected`
      }
    }
    return { data: rows, caption, fc, ond, ticks, domain, yticks, legend }
  }, [d, ts, farmer, lang, sc.season, sc.phase])
  const note = useYearNote(d, ts, year)
  if (data.filter((x) => !x.fc).length < 3) return null
  return (
    <ChartCard title={farmer ? t(lang!, ond ? 'fc.rain.title.ond' : 'trends.rain.title') : ond ? 'Winter-season rain compared with normal, each year' : 'Monsoon rain compared with normal, each year'} caption={caption} source={farmer ? undefined : 'India Meteorological Department gridded rainfall; El Niño years from NOAA; expected rain from the season outlook, TimesFM range from the Google TimesFM forecast'}
      right={<span className="flex items-center gap-2 md-label-medium text-muted"><i className="inline-block h-3 w-3 rounded-sm" style={{ background: C.act }} />drier<i className="inline-block h-3 w-3 rounded-sm" style={{ background: C.info }} />wetter</span>}>
      <div role="img" aria-label={note ?? `Bar chart of ${ond ? 'winter-season' : 'monsoon'} rain compared with normal by year${fc ? `; expected ${fc.window} ${fc.year}: ${signed(fc.v)}` : ''}`}>
        <ResponsiveContainer width="100%" height={farmer ? 190 : 160}>
          <BarChart data={data} margin={{ top: 18, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={C.line} vertical={false} />
            <XAxis dataKey="year" {...AXIS} {...(ticks ? { ticks, interval: 0 } : { interval: 4 })} />
            <YAxis {...AXIS} tickFormatter={(v: number) => `${v}%`} width={44} {...(domain ? { domain, ticks: yticks } : {})} />
            <ReferenceLine y={0} stroke={C.muted} />
            <Tooltip content={<Tip render={(p) => p.fc && fc
              ? <><b>{fc.window} {String(p.year)}</b><span className="text-inverse-primary"> · expected</span><br />{signed(fc.v)} vs normal rain{fc.tfm && <><br />TimesFM: {signed(fc.tfm.med)}, range {signed(fc.tfm.p10)} to {signed(fc.tfm.p90)}<br /><span className="text-inverse-primary">little skill at district level</span></>}</>
              : <><b>{String(p.year)}</b>{p.el ? <span className="text-inverse-primary"> · El Niño year</span> : null}<br />{p.v == null ? 'No data' : `${signed(p.v as number)} vs normal rain`}</>} />} />
            <Bar dataKey="v" isAnimationActive={false}>
              {data.map((x) => <Cell key={x.year} fill={x.v != null && x.v < 0 ? C.act : C.info} fillOpacity={0.85} stroke={x.el ? C.ink : 'none'} strokeWidth={x.el ? 1.5 : 0} />)}
            </Bar>
            {fc && <Customized component={<RainFcLayer fy={String(fc.year)} v={fc.v} tfm={fc.tfm} uid={uid} />} />}
            {year != null && <ReferenceLine x={String(year)} stroke={C.ink} strokeDasharray="4 3" label={{ value: String(year), position: 'top', fontSize: 11, fill: C.ink }} />}
          </BarChart>
        </ResponsiveContainer>
      </div>
      {fc && <FcLegend items={[{ k: 'hatch', label: legend }, ...(fc.tfm ? [{ k: 'whisker' as const, label: farmer ? t(lang!, 'fc.tfm') : 'TimesFM range' }] : [])]} />}
    </ChartCard>
  )
}

// ------------------------------------------------------------------ nutrition NFHS small multiples
const ROUND_BY_YEAR: [RegExp, string][] = [[/^2015/, 'NFHS-4'], [/^2019/, 'NFHS-5'], [/^2023|^2024/, 'NFHS-6']]
interface NfhsRow { year: string; round: string; v: Record<string, number | null> }
const MEASURES: { k: string; title: string; long: string }[] = [
  { k: 'stunting', title: 'Stunting (height-for-age)', long: 'stunting' },
  { k: 'wasting', title: 'Wasting (weight-for-height)', long: 'wasting' },
  { k: 'underweight', title: 'Underweight (weight-for-age)', long: 'underweight' },
  { k: 'child_anaemia', title: 'Anaemia (children 6–59 months)', long: 'child anaemia' },
]
function nfhsRows(d: District, ts: Timeseries | null): NfhsRow[] {
  const mk = (year: string, o: Rec): NfhsRow => ({ year, round: ROUND_BY_YEAR.find(([re]) => re.test(year))?.[1] ?? year, v: Object.fromEntries(MEASURES.map((m) => [m.k, numOrNull(o[m.k])])) })
  let rows = (ts?.nfhs ?? []).filter(isRec).map((o) => mk(String(o.year ?? ''), o)).filter((r) => r.year)
  if (rows.length < 2) {
    const n = d.nutrition as unknown as Rec | null
    rows = ['nfhs4', 'nfhs5', 'nfhs6'].map((k) => (isRec(n?.[k]) ? mk(String((n![k] as Rec).year ?? k), n![k] as Rec) : null)).filter((x): x is NfhsRow => x != null)
  }
  return rows.sort((a, b) => a.year.localeCompare(b.year))
}
export function NutritionMultiples({ d, ts }: { d: District; ts: Timeseries | null }) {
  const rows = useMemo(() => nfhsRows(d, ts), [d, ts])
  if (rows.length < 2) return null
  const panels = MEASURES.map((m) => {
    const data = rows.map((r) => ({ round: r.round, v: r.v[m.k] }))
    const vals = data.filter((x) => x.v != null) as { round: string; v: number }[]
    if (vals.length < 2) return null
    const delta = vals[vals.length - 1].v - vals[0].v
    return { m, data, vals, delta }
  }).filter((x): x is NonNullable<typeof x> => x != null)
  if (!panels.length) return null
  return (
    <ChartCard
      title="Children's nutrition across three national surveys"
      caption="Share of children under 5 affected, from the national family health survey (NFHS). Lower is better."
      source="National Family Health Survey rounds 4, 5 and 6 (district estimates)"
    >
      <div className="grid grid-cols-2 gap-3">
        {panels.map(({ m, data, vals, delta }) => {
          const worse = delta > 0.5, better = delta < -0.5
          return (
            <div key={m.k} className="rounded-m3-md border border-outline-variant p-3">
              <div className="md-label-large text-on-surface">{m.title}</div>
              <div className={`flex items-center gap-0.5 md-label-medium ${worse ? 'text-act-ink' : better ? 'text-low-ink' : 'text-muted'}`}>
                {worse && <Icon name="arrow_upward" size={14} />}{better && <Icon name="arrow_downward" size={14} />}{Math.abs(delta) < 0.5 ? 'No big change' : `${Math.abs(delta).toFixed(0)} points ${worse ? 'worse' : 'better'} since ${vals[0].round}`}
              </div>
              <div role="img" aria-label={`${m.long}: ${vals.map((x) => `${x.round} ${x.v.toFixed(0)} %`).join(', ')}`}>
                <ResponsiveContainer width="100%" height={104}>
                  <LineChart data={data} margin={{ top: 18, right: 18, left: 18, bottom: 0 }}>
                    <XAxis dataKey="round" {...AXIS} tick={{ fill: C.muted, fontSize: 9 }} axisLine={false} interval={0} />
                    <YAxis hide domain={[0, (max: number) => Math.ceil(max * 1.1)]} />
                    <Line type="monotone" dataKey="v" stroke={worse ? C.act : C.accent} strokeWidth={2} dot={{ r: 3, fill: C.surface, strokeWidth: 2 }} connectNulls isAnimationActive={false}>
                      <LabelList dataKey="v" position="top" formatter={(v: number) => (v == null ? '' : `${v.toFixed(0)}%`)} style={{ fontSize: 10, fill: C.ink, fontWeight: 600 }} />
                    </Line>
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )
        })}
      </div>
    </ChartCard>
  )
}

// ------------------------------------------------------------------ Poshan monthly underweight
export function PoshanChart({ d }: { d: District }) {
  const { data, caption, fc } = useMemo(() => {
    const raw = (d.nutrition?.poshan_live as unknown as Rec | null)?.series
    if (!isRec(raw)) return { data: [], caption: '', fc: null }
    const months = Object.keys(raw).filter((k) => numOrNull(raw[k]) != null).sort()
    const obs = months.map((m) => ({ m, label: monthName(m), v: raw[m] as number }))
    const last = obs[obs.length - 1], prev = obs[obs.length - 13] ?? obs[0]
    const diff = last && prev ? last.v - prev.v : 0
    const ps = poshanOf(d)
    let caption = last ? `${last.v.toFixed(0)}${NB}% of children weighed at anganwadis in ${monthName(last.m, true)} were underweight${Math.abs(diff) >= 1 && prev !== last ? `, ${diff > 0 ? 'up' : 'down'} ${Math.abs(diff).toFixed(0)} points from ${monthName(prev.m, true)}` : ', about the same as a year earlier'}.${ps?.underweight != null ? '' : ''}` : ''
    const fc = last && obs.length >= 3 ? poshanForecast(d, last.m, last.v) : null
    const data: { m: string; label: string; v: number | null; p?: number | null; fc?: boolean }[] = obs.map((o) => ({ ...o, ...(fc ? { p: o === last ? o.v : null } : {}) }))
    if (fc) {
      fc.points.forEach((x, i) => data.push({ m: x.m, label: monthName(x.m), v: null, p: x.v, fc: i === fc.points.length - 1 }))
      caption += ` Projected to reach about ${fc.target.toFixed(0)}${NB}% by ${monthName(fc.end, true)} (indicative).`
    }
    return { data, caption, fc }
  }, [d])
  if (data.filter((x) => !x.fc && x.v != null).length < 3) return null
  return (
    <ChartCard title="Underweight children, month by month" caption={caption} source="Poshan Tracker (anganwadi growth monitoring), Ministry of Women and Child Development; projection from Google TimesFM (national signal, little skill at district level)">
      <div role="img" aria-label={caption}>
        <ResponsiveContainer width="100%" height={150}>
          <LineChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={C.line} vertical={false} />
            <XAxis dataKey="label" {...AXIS} interval={Math.max(1, Math.floor(data.length / 5))} />
            <YAxis {...AXIS} tickFormatter={(v: number) => `${v}%`} domain={['auto', 'auto']} width={44} />
            <Tooltip content={<Tip render={(p) => <><b>{monthName(String(p.m), true)}</b>{p.v == null ? <span className="text-inverse-primary"> · projected</span> : null}<br />{(((p.v ?? p.p) as number)).toFixed(0)}{NB}% underweight</>} />} />
            <Line type="monotone" dataKey="v" stroke={C.act} strokeWidth={2.25} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
            {fc && <Line type="linear" dataKey="p" stroke={C.accent} strokeWidth={2} strokeDasharray="5 4" connectNulls isAnimationActive={false} activeDot={false}
              dot={(q: { cx?: number; cy?: number; index?: number; payload?: { fc?: boolean } }) => (q.payload?.fc && q.cx != null && q.cy != null ? <circle key={`pf-${q.index}`} cx={q.cx} cy={q.cy} r={4.5} fill={C.bg} stroke={C.accent} strokeWidth={2} /> : <g key={`pf-${q.index}`} />)} />}
          </LineChart>
        </ResponsiveContainer>
      </div>
      {fc && <div className="mt-1 flex items-center gap-1.5 md-label-medium text-muted"><Swatch k="dash" />Projected (TimesFM)</div>}
    </ChartCard>
  )
}

// ------------------------------------------------------------------ PDS monthly offtake
export function PdsChart({ ts }: { ts: Timeseries | null }) {
  const { data, caption } = useMemo(() => {
    const rows = (ts?.pds_monthly ?? []).filter((r) => r.date)
    const data = rows.map((r) => ({ date: r.date, label: monthName(r.date.slice(0, 7)), rice: r.rice_t ?? 0, wheat: r.wheat_t ?? 0 }))
    const last = data[data.length - 1]
    const caption = last ? `Rice and wheat handed out through ration shops each month. In ${monthName(last.date.slice(0, 7), true)} about ${Math.round(last.rice + last.wheat).toLocaleString('en-IN')} tonnes were lifted.` : ''
    return { data, caption }
  }, [ts])
  if (data.length < 3) return null
  return (
    <ChartCard title="Grain given out at ration shops, month by month" caption={caption} source="monthly public distribution system (PDS) offtake records"
      right={<span className="flex items-center gap-2 md-label-medium text-muted"><i className="inline-block h-3 w-3 rounded-sm" style={{ background: C.accent }} />rice<i className="inline-block h-3 w-3 rounded-sm" style={{ background: C.watch }} />wheat</span>}>
      <div role="img" aria-label={caption}>
        <ResponsiveContainer width="100%" height={160}>
          <AreaChart data={data} margin={{ top: 6, right: 8, left: -6, bottom: 0 }}>
            <CartesianGrid stroke={C.line} vertical={false} />
            <XAxis dataKey="label" {...AXIS} interval={Math.max(1, Math.floor(data.length / 6))} />
            <YAxis {...AXIS} tickFormatter={(v: number) => (v >= 1000 ? `${v / 1000}k` : String(v))} width={40} />
            <Tooltip content={<Tip render={(p) => <><b>{monthName(String(p.date).slice(0, 7), true)}</b><br />Rice {Math.round(p.rice as number).toLocaleString('en-IN')} t<br />Wheat {Math.round(p.wheat as number).toLocaleString('en-IN')} t</>} />} />
            <Area type="monotone" stackId="1" dataKey="rice" stroke={C.accent} fill={C.accent} fillOpacity={0.35} isAnimationActive={false} />
            <Area type="monotone" stackId="1" dataKey="wheat" stroke={C.watch} fill={C.watch} fillOpacity={0.35} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  )
}

// ------------------------------------------------------------------ prices
export function PriceChart({ d }: { d: District }) {
  const m = useMemo(() => marketsOf(d), [d])
  if (!m || m.series.length < 3) return null
  const sp = m.spike
  const caption = `What farmers got for ${m.crop ? m.crop.toLowerCase() : 'the main grain'} at harvest, in rupees per quintal (not adjusted for inflation).${sp != null && Math.abs(sp) >= 1 ? ` In El Niño years the price moved ${sp > 0 ? 'up' : 'down'} about ${Math.round(Math.abs(sp))}${NB}% compared with its usual trend.` : ''}`
  return (
    <ChartCard title={`Farm-gate price${m.crop ? `: ${m.crop}` : ''}`} caption={caption} source="ICRISAT district-level farm harvest prices">
      <div role="img" aria-label={caption}>
        <ResponsiveContainer width="100%" height={150}>
          <LineChart data={m.series} margin={{ top: 6, right: 8, left: -6, bottom: 0 }}>
            <CartesianGrid stroke={C.line} vertical={false} />
            <XAxis dataKey="x" {...AXIS} interval="preserveStartEnd" />
            <YAxis {...AXIS} tickFormatter={(v: number) => (v >= 1000 ? `${v / 1000}k` : String(v))} width={40} />
            <Tooltip content={<Tip render={(p) => <><b>{String(p.x)}</b><br />₹{Math.round(p.y as number).toLocaleString('en-IN')} per quintal</>} />} />
            <Line type="monotone" dataKey="y" stroke={C.info} strokeWidth={2.25} dot={{ r: 2.5 }} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  )
}

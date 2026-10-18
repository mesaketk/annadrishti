import type { ReactNode } from 'react'
import { useMemo } from 'react'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, LabelList, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { marketsOf, poshanOf } from '../../lib/extra'
import { bandOf, thresholdsOf } from '../../lib/scales'
import { useStore } from '../../lib/store'
import type { District, Lang, Timeseries } from '../../types'
import { AXIS, C } from './theme'
import { isEl, lightOf, mean, monthName, NB } from './copy'
import { t } from './i18n'
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

// ------------------------------------------------------------------ yield
export function YieldChart({ d, ts, year, lang }: { d: District; ts: Timeseries; year?: number; lang?: Lang }) {
  const farmer = lang != null
  const { data, ymax, caption } = useMemo(() => {
    const ys = ts.yield.foodgrain_t_ha ?? {}
    const years = Object.keys(ys).filter((y) => +y >= 2000 && +y <= 2024).sort()
    const vals = years.map((y) => ys[y]).filter((v): v is number => v != null)
    const ymax = Math.max(0.5, Math.ceil(Math.max(0.1, ...vals) * 1.08 * 2) / 2)
    const el = (y: string) => isEl(ts.oni_phase?.[y])
    const data = years.map((y) => ({ year: y, y: ys[y], enso: el(y) ? ymax : null }))
    const first = mean(years.slice(0, 5).map((y) => ys[y]).filter((v): v is number => v != null))
    const last = mean(years.slice(-5).map((y) => ys[y]).filter((v): v is number => v != null))
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
    return { data, ymax, caption }
  }, [ts, d, farmer, lang])
  const note = useYearNote(d, ts, year)
  if (data.length < 3) return null
  return (
    <ChartCard title={farmer ? t(lang!, 'trends.yield.title') : 'Grain harvested per hectare, 2000–2024'} caption={caption} source={farmer ? undefined : 'crop statistics from the Ministry of Agriculture (area, production, yield); El Niño years from NOAA'}
      right={<span className="flex items-center gap-1.5 md-label-medium text-muted"><i className="inline-block h-3 w-3 rounded-sm" style={{ background: C.elnino, border: `1px solid ${C.act}55` }} />El Niño</span>}>
      <div role="img" aria-label={note ?? 'Line chart of grain yield per hectare by year, El Niño years shaded'}>
        <ResponsiveContainer width="100%" height={farmer ? 190 : 170}>
          <ComposedChart data={data} margin={{ top: 18, right: 8, left: -14, bottom: 0 }} barCategoryGap={0}>
            <CartesianGrid stroke={C.line} vertical={false} />
            <XAxis dataKey="year" {...AXIS} interval={4} />
            <YAxis {...AXIS} domain={[0, ymax]} tickCount={5} tickFormatter={(v: number) => v.toFixed(1)} width={40} />
            <Tooltip content={<Tip render={(p) => <><b>{String(p.year)}</b>{p.enso != null && <span className="text-inverse-primary"> · El Niño year</span>}<br />{p.y == null ? 'No data' : `${(p.y as number).toFixed(2)} tonnes per hectare`}</>} />} />
            <Bar dataKey="enso" fill={C.elnino} isAnimationActive={false} legendType="none" />
            <Line type="monotone" dataKey="y" stroke={C.accent} strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} connectNulls isAnimationActive={false} />
            {year != null && <ReferenceLine x={String(year)} stroke={C.ink} strokeDasharray="4 3" label={{ value: String(year), position: 'top', fontSize: 11, fill: C.ink }} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  )
}

// ------------------------------------------------------------------ rain
export function RainChart({ d, ts, year, lang }: { d: District; ts: Timeseries | null; year?: number; lang?: Lang }) {
  const farmer = lang != null
  const { data, caption } = useMemo(() => {
    const fromTs = isRec((ts as unknown as Rec | null)?.jjas_anomaly_pct) ? ((ts as unknown as Rec).jjas_anomaly_pct as Record<string, number | null>) : null
    const a = d.climate?.jjas_anomaly_pct ?? fromTs ?? {}
    const years = Object.keys(a).filter((y) => a[y] != null && +y >= 2000).sort()
    const data = years.map((y) => ({ year: y, v: a[y] as number, el: isEl(ts?.oni_phase?.[y]) }))
    const below = data.filter((x) => x.v < 0).length
    const elAvg = d.climate?.elnino_mean_anomaly_pct ?? mean(data.filter((x) => x.el).map((x) => x.v))
    let caption: string
    if (farmer) caption = elAvg != null && elAvg < -1 ? t(lang!, 'trends.rain.cap.n', { n: Math.round(Math.abs(elAvg)) }) : t(lang!, 'trends.rain.cap')
    else {
      caption = `Monsoon rain (June–September) was below normal in ${below} of the last ${data.length} years.` + (elAvg != null ? ` In El Niño years it averaged ${Math.round(Math.abs(elAvg))}${NB}% ${elAvg < 0 ? 'below' : 'above'} normal${d.climate?.jjas_normal_mm ? ` (normal is about ${Math.round(d.climate.jjas_normal_mm)} mm)` : ''}.` : '')
    }
    return { data, caption }
  }, [d, ts, farmer, lang])
  const note = useYearNote(d, ts, year)
  if (data.length < 3) return null
  return (
    <ChartCard title={farmer ? t(lang!, 'trends.rain.title') : 'Monsoon rain compared with normal, each year'} caption={caption} source={farmer ? undefined : 'India Meteorological Department gridded rainfall; El Niño years from NOAA'}
      right={<span className="flex items-center gap-2 md-label-medium text-muted"><i className="inline-block h-3 w-3 rounded-sm" style={{ background: C.act }} />drier<i className="inline-block h-3 w-3 rounded-sm" style={{ background: C.info }} />wetter</span>}>
      <div role="img" aria-label={note ?? 'Bar chart of monsoon rain compared with normal by year'}>
        <ResponsiveContainer width="100%" height={farmer ? 190 : 160}>
          <BarChart data={data} margin={{ top: 18, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={C.line} vertical={false} />
            <XAxis dataKey="year" {...AXIS} interval={4} />
            <YAxis {...AXIS} tickFormatter={(v: number) => `${v}%`} width={44} />
            <ReferenceLine y={0} stroke={C.muted} />
            <Tooltip content={<Tip render={(p) => <><b>{String(p.year)}</b>{p.el ? <span className="text-inverse-primary"> · El Niño year</span> : null}<br />{signed(p.v as number)} vs normal rain</>} />} />
            <Bar dataKey="v" isAnimationActive={false}>
              {data.map((x) => <Cell key={x.year} fill={x.v < 0 ? C.act : C.info} fillOpacity={0.85} stroke={x.el ? C.ink : 'none'} strokeWidth={x.el ? 1.5 : 0} />)}
            </Bar>
            {year != null && <ReferenceLine x={String(year)} stroke={C.ink} strokeDasharray="4 3" label={{ value: String(year), position: 'top', fontSize: 11, fill: C.ink }} />}
          </BarChart>
        </ResponsiveContainer>
      </div>
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
  const { data, caption } = useMemo(() => {
    const raw = (d.nutrition?.poshan_live as unknown as Rec | null)?.series
    if (!isRec(raw)) return { data: [], caption: '' }
    const months = Object.keys(raw).filter((k) => numOrNull(raw[k]) != null).sort()
    const data = months.map((m) => ({ m, label: monthName(m), v: raw[m] as number }))
    const last = data[data.length - 1], prev = data[data.length - 13] ?? data[0]
    const diff = last && prev ? last.v - prev.v : 0
    const ps = poshanOf(d)
    const caption = last ? `${last.v.toFixed(0)}${NB}% of children weighed at anganwadis in ${monthName(last.m, true)} were underweight${Math.abs(diff) >= 1 && prev !== last ? `, ${diff > 0 ? 'up' : 'down'} ${Math.abs(diff).toFixed(0)} points from ${monthName(prev.m, true)}` : ', about the same as a year earlier'}.${ps?.underweight != null ? '' : ''}` : ''
    return { data, caption }
  }, [d])
  if (data.length < 3) return null
  return (
    <ChartCard title="Underweight children, month by month" caption={caption} source="Poshan Tracker (anganwadi growth monitoring), Ministry of Women and Child Development">
      <div role="img" aria-label={caption}>
        <ResponsiveContainer width="100%" height={150}>
          <LineChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={C.line} vertical={false} />
            <XAxis dataKey="label" {...AXIS} interval={Math.max(1, Math.floor(data.length / 5))} />
            <YAxis {...AXIS} tickFormatter={(v: number) => `${v}%`} domain={['auto', 'auto']} width={44} />
            <Tooltip content={<Tip render={(p) => <><b>{monthName(String(p.m), true)}</b><br />{(p.v as number).toFixed(0)}{NB}% underweight</>} />} />
            <Line type="monotone" dataKey="v" stroke={C.act} strokeWidth={2.25} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
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

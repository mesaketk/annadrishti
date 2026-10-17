import { useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { useStore } from '../lib/store'
import { actionsCsvUrl, getActions, getStateBrief, rowsToCsv, type ActionsResult } from '../lib/api'
import { fmtCompact, fmtNum } from '../lib/format'
import { useScenario } from '../lib/useScenario'
import type { ActionRow, Band } from '../types'
import { DEPARTMENTS } from '../lib/plain'
import type { Department } from '../types'
import { BandPill, Button, ErrorNote, Icon, IconButton, Sheet, SelectField, Skeleton, Stat } from './ui'
import { useMedia } from '../lib/useMedia'

type SortKey = keyof ActionRow
const noPrepos = (r: ActionRow) => r.grain_preposition_t === 0 && r.pulses_preposition_t === 0
const dash = <span className="text-muted" title="Not needed">–</span>
const COLS: { k: SortKey; label: string; num?: boolean; render?: (r: ActionRow) => React.ReactNode; title?: string; depts?: Department[] }[] = [
  { k: 'priority_rank_national', label: 'Priority', num: true, title: 'National priority order: 1 = act first', render: (r) => r.priority_rank_national ?? '–' },
  { k: 'district', label: 'District' },
  { k: 'state', label: 'State' },
  { k: 'score', label: 'Risk level', render: (r) => <span className="inline-flex items-center gap-1.5"><BandPill band={r.band} /></span> },
  { k: 'grain_preposition_t', label: 'Extra grain (tonnes)', num: true, depts: ['food_civil_supplies'], title: 'Extra rice, wheat or millet to move in advance through ration shops (PDS/OMSS)', render: (r) => noPrepos(r) ? dash : fmtNum(r.grain_preposition_t) },
  { k: 'pulses_preposition_t', label: 'Pulses (tonnes)', num: true, depts: ['food_civil_supplies'], render: (r) => noPrepos(r) ? dash : fmtNum(r.pulses_preposition_t) },
  { k: 'anganwadi_children', label: 'Children needing extra nutrition', num: true, depts: ['wcd_icds', 'health'], title: 'Children under 5 to reach with extra Anganwadi food', render: (r) => fmtNum(r.anganwadi_children) },
  { k: 'women_anaemia_target', label: 'Women with anaemia to reach', num: true, depts: ['health', 'wcd_icds'], render: (r) => fmtNum(r.women_anaemia_target) },
  { k: 'seed_bank_ha', label: 'Seed to stock (hectares)', num: true, depts: ['agriculture'], title: 'Area that can be sown from short-duration or millet seed kept in reserve', render: (r) => r.seed_bank_ha ? fmtNum(r.seed_bank_ha) : dash },
  { k: 'mgnrega_persondays', label: 'Rural work days (MGNREGA)', num: true, depts: ['rural_development'], render: (r) => r.mgnrega_persondays ? fmtCompact(r.mgnrega_persondays) : dash },
  { k: 'pmfby_gap_farmers', label: 'Farmers without crop insurance', num: true, depts: ['agriculture'], title: 'Farmers not yet covered by PMFBY crop insurance', render: (r) => fmtNum(r.pmfby_gap_farmers) },
  { k: 'fodder_flag', label: 'Fodder needed', depts: ['animal_husbandry'], render: (r) => r.fodder_flag ? <span className="font-medium text-watch-ink">Yes</span> : dash },
  { k: 'lead_rabi', label: 'Act by', render: (r) => <span className="whitespace-nowrap text-muted">{[r.lead_rabi && `Rabi ${r.lead_rabi.replace('by ', '')}`, r.lead_kharif && `Kharif ${r.lead_kharif.replace('by ', '')}`].filter(Boolean).join(' · ') || '–'}</span> },
]
const BASE_COLS = new Set<SortKey>(['priority_rank_national', 'district', 'state', 'score', 'lead_rabi'])
// "all departments" hides the two niche columns to keep the table readable
const ALL_HIDDEN = new Set<SortKey>(['women_anaemia_target', 'fodder_flag'])

export default function Planner() {
  const { districts, kpis, mock, select, setView } = useStore()
  const { season, phase, gkey, key: keyOf, label: scLabel } = useScenario()
  const wide = useMedia('(min-width: 1024px)')
  const [res, setRes] = useState<ActionsResult | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [state, setState] = useState('')
  const [band, setBand] = useState<'' | Band>('')
  const [dept, setDept] = useState<'' | Department>('')
  const [sort, setSort] = useState<{ k: SortKey; dir: 1 | -1 }>({ k: 'priority_rank_national', dir: 1 })
  const [brief, setBrief] = useState<{ state: string; md: string | null; loading: boolean; err: string | null } | null>(null)

  useEffect(() => {
    if (!kpis) return
    let c = false
    setRes(null); setErr(null)
    getActions(season, phase, districts, kpis, mock).then((r) => !c && setRes(r)).catch((e: Error) => !c && setErr(e.message))
    return () => { c = true }
  }, [season, phase, districts, kpis, mock])

  const cols = useMemo(() => COLS.filter((c) => (dept ? BASE_COLS.has(c.k) || c.depts?.includes(dept) : !ALL_HIDDEN.has(c.k))), [dept])
  const states = useMemo(() => [...new Set((res?.rows ?? []).map((r) => r.state))].sort(), [res])
  const rows = useMemo(() => {
    let r = res?.rows ?? []
    if (state) r = r.filter((x) => x.state === state)
    if (band) r = r.filter((x) => x.band === band)
    const { k, dir } = sort
    return [...r].sort((a, b) => {
      const x = a[k], y = b[k]
      if (x == null && y == null) return 0
      if (x == null) return 1
      if (y == null) return -1
      return (x < y ? -1 : x > y ? 1 : 0) * dir
    })
  }, [res, state, band, sort])

  const t = res?.totals
  const coverage = useMemo(() => {
    const noData = districts.filter((d) => d.risk[keyOf(d)]?.band === 'no_data').length
    return { noData, scored: districts.length - noData }
  }, [districts, keyOf])
  const filtered = state !== '' || band !== ''
  const sumF = (k: SortKey) => rows.reduce((a, r) => a + (Number(r[k]) || 0), 0)

  const download = () => {
    if (!mock) { window.location.href = actionsCsvUrl(gkey, state, band); return }
    const blob = new Blob([rowsToCsv(rows)], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob); a.download = `annadrishti_actions_${gkey.replace(':', '_')}.csv`; a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  }

  const briefState = state || kpis?.top_states?.[0]?.state || states[0] || ''
  const genBrief = async () => {
    if (!briefState) return
    setBrief({ state: briefState, md: null, loading: true, err: null })
    try {
      const md = await getStateBrief(briefState, gkey, districts, mock)
      setBrief({ state: briefState, md, loading: false, err: null })
    } catch (e) {
      setBrief({ state: briefState, md: null, loading: false, err: e instanceof Error ? e.message : 'Failed' })
    }
  }
  const show = (k: SortKey) => !dept || BASE_COLS.has(k) || COLS.find((c) => c.k === k)?.depts?.includes(dept)
  const briefBody = brief && (
    <div className="p-4">
      {brief.loading && <div className="space-y-2">{Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} className="h-3" />)}<div className="md-body-small text-muted">Drafting the plan…</div></div>}
      {brief.err && <ErrorNote onRetry={genBrief}>Could not write the plan: {brief.err}</ErrorNote>}
      {brief.md && (
        <>
          <div className="md"><ReactMarkdown>{brief.md}</ReactMarkdown></div>
          <Button size="sm" className="mt-3" onClick={() => navigator.clipboard?.writeText(brief.md!)} iconLeft={<Icon name="content_copy" size={18} />}>Copy text</Button>
        </>
      )}
    </div>
  )

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="shrink-0 space-y-3 border-b border-outline-variant bg-surface px-3 py-3">
          <div className="hide-scrollbar flex gap-2 overflow-x-auto [&>*]:min-w-[190px] [&>*]:flex-1">
            {show('grain_preposition_t') && <Stat dense label="Extra grain to move in advance" value={t?.grain_preposition_t == null ? '–' : fmtCompact(t.grain_preposition_t)} unit="tonnes" sub={filtered ? `filtered: ${fmtCompact(sumF('grain_preposition_t'))} tonnes` : 'through ration shops, all districts'} />}
            {show('pulses_preposition_t') && <Stat dense label="Pulses" value={t?.pulses_preposition_t == null ? '–' : fmtCompact(t.pulses_preposition_t)} unit="tonnes" sub={filtered ? `filtered: ${fmtCompact(sumF('pulses_preposition_t'))} tonnes` : undefined} />}
            {show('anganwadi_children') && <Stat dense label="Children needing extra nutrition" value={fmtCompact(t?.anganwadi_children)} unit="children" sub={filtered ? `filtered: ${fmtCompact(sumF('anganwadi_children'))}` : 'Anganwadi top-up'} />}
            {show('seed_bank_ha') && <Stat dense label="Reserve seed for" value={t?.seed_bank_ha == null ? '–' : fmtCompact(t.seed_bank_ha)} unit="hectares" sub={filtered ? `filtered: ${fmtCompact(sumF('seed_bank_ha'))}` : 'short-duration or millet seed'} />}
            {show('mgnrega_persondays') && <Stat dense label="Rural work days to open" value={fmtCompact(t?.mgnrega_persondays)} unit="days (MGNREGA)" sub={filtered ? `filtered: ${fmtCompact(sumF('mgnrega_persondays'))}` : 'in Act-now districts'} />}
            {show('pmfby_gap_farmers') && <Stat dense label="Farmers without crop insurance" value={fmtCompact(t?.pmfby_gap_farmers)} unit="farmers" sub={filtered ? `filtered: ${fmtCompact(sumF('pmfby_gap_farmers'))}` : 'not yet in PMFBY'} />}
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-3 md-body-medium">
            <span className="md-title-small">{scLabel}</span>
            <span className="text-muted">· {rows.length} districts</span>
            <span className="text-muted" title="Districts without enough farm data get no estimate and no actions">· {coverage.scored} with an estimate · {coverage.noData} without</span>
            <SelectField label="Department" dense value={dept} onChange={(v) => setDept(v as '' | Department)} className="min-w-[170px] sm:ml-3">
              <option value="">All departments</option>
              {DEPARTMENTS.map((d) => <option key={d.id} value={d.id}>{d.short}</option>)}
            </SelectField>
            <SelectField label="State" dense value={state} onChange={setState} className="min-w-[150px]">
              <option value="">All states</option>
              {states.map((s) => <option key={s}>{s}</option>)}
            </SelectField>
            <SelectField label="Risk level" dense value={band} onChange={(v) => setBand(v as '' | Band)} className="min-w-[150px]">
              <option value="">All risk levels</option><option value="high">Act now</option><option value="medium">Watch</option><option value="low">Low risk</option>
            </SelectField>
            <div className="flex gap-2 sm:ml-auto">
              <Button size="sm" onClick={download} iconLeft={<Icon name="download" size={18} />}>Download table (CSV)</Button>
              <Button size="sm" variant="primary" onClick={genBrief} disabled={!briefState || brief?.loading} iconLeft={<Icon name="auto_awesome" size={18} />}>Write state plan{briefState ? ` · ${briefState}` : ''}</Button>
            </div>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto bg-surface" data-scroll-root>
          {err && <div className="p-3"><ErrorNote>Could not load the plan: {err}</ErrorNote></div>}
          {!res && !err && <div className="space-y-2 p-3">{Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}</div>}
          {res && (
            <table className="w-full border-separate border-spacing-0 md-body-medium">
              <thead className="sticky top-0 z-10 bg-surface-container-low">
                <tr>
                  {cols.map((c) => (
                    <th
                      key={c.k} title={c.title} aria-sort={sort.k === c.k ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}
                      onClick={() => setSort((s) => ({ k: c.k, dir: s.k === c.k ? (s.dir === 1 ? -1 : 1) : c.num ? -1 : 1 }))}
                      className={`cursor-pointer select-none border-b border-outline-variant bg-surface-container-low px-3 py-3 align-bottom md-label-medium text-on-surface-variant hover:text-on-surface ${c.num ? 'text-right' : 'text-left'}`}
                    >
                      {c.label}{sort.k === c.k && <Icon name={sort.dir === 1 ? 'arrow_upward' : 'arrow_downward'} size={14} className="ml-0.5 align-text-bottom" />}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.lgd} onClick={() => { select(r.lgd, true); setView('map') }} className="cursor-pointer transition-colors hover:bg-surface-container">
                    {cols.map((c) => (
                      <td key={c.k} className={`border-b border-outline-variant px-3 py-3 tabular-nums ${c.num ? 'text-right' : ''} ${c.k === 'district' ? 'font-medium' : ''}`}>
                        {c.render ? c.render(r) : String(r[c.k] ?? '–')}
                      </td>
                    ))}
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan={cols.length} className="p-8 text-center text-muted">No districts match these filters.</td></tr>}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {brief && wide && (
        <aside className="flex h-full w-[420px] shrink-0 flex-col border-l border-outline-variant bg-surface" aria-label="State plan">
          <div className="flex items-center justify-between border-b border-outline-variant p-3 pl-4">
            <div>
              <div className="flex items-center gap-1 md-label-medium text-muted"><Icon name="auto_awesome" size={16} className="text-primary" fill /> State plan</div>
              <div className="md-title-medium">{brief.state} · {scLabel}</div>
            </div>
            <IconButton icon="close" label="Close plan" onClick={() => setBrief(null)} />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">{briefBody}</div>
        </aside>
      )}
      {!wide && <Sheet open={!!brief} onClose={() => setBrief(null)} side="bottom" title={brief ? `${brief.state} · state plan` : ''}>{briefBody}</Sheet>}
    </div>
  )
}

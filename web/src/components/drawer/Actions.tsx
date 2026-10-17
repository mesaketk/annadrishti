import { useMemo } from 'react'
import { normalizeRow, rowsToCsv } from '../../lib/api'
import { DEPARTMENTS } from '../../lib/extra'
import type { Department, District, Risk } from '../../types'
import { bigNum, leadDate, NB, tonnes } from './copy'
import { Icon, type IconName } from '../ui'
import { Button, Card, Pill } from './ui'

interface Item { icon: IconName; what: string; qty: string; dept: Department }
type Ex = NonNullable<Risk['actions']> & { protective_irrigation_ha?: number | null; groundwater_budget_flag?: boolean | null }

export function actionItems(a: Ex): Item[] {
  const out: Item[] = []
  if (a.grain_preposition_t) out.push({ icon: 'grass', what: 'Move extra grain (rice, wheat or millets) into district stock', qty: tonnes(a.grain_preposition_t), dept: 'food_civil_supplies' })
  if (a.pulses_preposition_t) out.push({ icon: 'nutrition', what: 'Stock pulses for ration shops and anganwadis', qty: tonnes(a.pulses_preposition_t), dept: 'food_civil_supplies' })
  if (a.anganwadi_children) out.push({ icon: 'child_care', what: 'Top up take-home nutrition for children under 5', qty: `${bigNum(a.anganwadi_children)} children`, dept: 'wcd_icds' })
  if (a.women_anaemia_target) out.push({ icon: 'bloodtype', what: 'Check women for anaemia and give iron tablets', qty: `${bigNum(a.women_anaemia_target)} women`, dept: 'health' })
  if (a.seed_bank_ha) out.push({ icon: 'eco', what: 'Keep short-duration and millet seed ready', qty: `enough for ${bigNum(a.seed_bank_ha)} hectares`, dept: 'agriculture' })
  if (a.protective_irrigation_ha) out.push({ icon: 'water_drop', what: 'Plan one or two protective irrigations for standing crops', qty: `${bigNum(a.protective_irrigation_ha)} hectares`, dept: 'agriculture' })
  if (a.pmfby_gap_farmers) out.push({ icon: 'shield', what: 'Enrol farmers not yet covered by crop insurance (PMFBY)', qty: `${bigNum(a.pmfby_gap_farmers)} farmers`, dept: 'agriculture' })
  if (a.mgnrega_persondays) out.push({ icon: 'construction', what: 'Keep village works ready under MGNREGA', qty: `${bigNum(a.mgnrega_persondays)} person-days of work`, dept: 'rural_development' })
  if (a.groundwater_budget_flag) out.push({ icon: 'water_drop', what: 'Draw up a village groundwater budget before irrigation starts', qty: 'all stressed blocks', dept: 'rural_development' })
  if (a.fodder_flag) out.push({ icon: 'pets', what: 'Set up fodder banks and cattle camps', qty: 'where fodder is short', dept: 'animal_husbandry' })
  return out
}
const deptShort = (id: Department) => DEPARTMENTS.find((x) => x.id === id)?.short ?? id

export default function PrepositionCard({ d, r, scenarioKey, seasonId, seasonLabel }: { d: District; r: Risk | null; scenarioKey: string; seasonId: string | null; seasonLabel: string | null }) {
  const a = r?.actions as Ex | null | undefined
  const items = useMemo(() => (a ? actionItems(a) : []), [a])
  if (!a) return <Card title="What to prepare"><p className="md-body text-muted">No action plan is available for this district yet.</p></Card>
  const leads = Object.entries(a.lead ?? {})
  const lead = leadDate((seasonId && a.lead?.[seasonId]) || leads[0]?.[1])

  const download = () => {
    const row = normalizeRow({ ...a, lgd: d.lgd, district: d.district, state: d.state, score: r?.score, band: r?.band })
    const url = URL.createObjectURL(new Blob([rowsToCsv([row])], { type: 'text/csv;charset=utf-8' }))
    const el = document.createElement('a')
    el.href = url; el.download = `annadrishti_${d.district.toLowerCase().replace(/\W+/g, '_')}_${scenarioKey.replace(/\W+/g, '_')}.csv`
    document.body.appendChild(el); el.click(); el.remove()
    setTimeout(() => URL.revokeObjectURL(url), 2000)
  }

  return (
    <Card title={`What to prepare${seasonLabel ? ` for ${seasonLabel}` : ''}`} aside={lead ? <Pill tone="watch" className="whitespace-nowrap">{lead}</Pill> : undefined}>
      {(a.priority_rank_state != null || a.priority_rank_national != null) && (
        <p className="-mt-1 mb-3 md-body-medium text-muted">
          Priority: {a.priority_rank_state != null ? `number ${a.priority_rank_state} in ${d.state}` : ''}{a.priority_rank_state != null && a.priority_rank_national != null ? ', ' : ''}{a.priority_rank_national != null ? `number ${a.priority_rank_national} in India` : ''} (1 = first to help).
        </p>
      )}
      {items.length === 0 ? <p className="md-body text-muted">Nothing extra needs to be pre-positioned at this risk level.</p> : (
        <ul className="divide-y divide-outline-variant">
          {items.map((it) => (
            <li key={it.what} className="flex items-start gap-3 py-3">
              <span aria-hidden className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-secondary-container text-on-secondary-container"><Icon name={it.icon} size={22} /></span>
              <div className="min-w-0 flex-1">
                <div className="md-title-medium text-on-surface">{it.qty}</div>
                <div className="md-body text-on-surface-variant">{it.what}</div>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <Pill tone="info">{deptShort(it.dept)}</Pill>
                  {lead && <span className="md-body-small text-muted">{lead}</span>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-outline-variant pt-3">
        <Button variant="secondary" onClick={download} iconLeft={<Icon name="download" size={18} />}>Download CSV row</Button>
        <span className="md-body-small text-muted">One line with every quantity above, for spreadsheets.{NB}</span>
      </div>
    </Card>
  )
}

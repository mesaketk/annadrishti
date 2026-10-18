import { useMemo, useState } from 'react'
import { useStore } from '../lib/store'
import { useMedia } from '../lib/useMedia'
import { DEPARTMENTS } from '../lib/plain'
import { STATUSES, STATUS_LABEL, tracker, trackerCounts, trackerCsv, useTracker, type TrackedAction } from '../lib/tracker'
import { Button, Chip, Icon, IconButton, Pill, SelectField, Sheet } from './ui'

const deptLabel = (id: string) => DEPARTMENTS.find((d) => d.id === id)?.short ?? id

function Row({ lgd, a }: { lgd: number; a: TrackedAction }) {
  const set = (patch: Partial<TrackedAction>) => tracker.update(lgd, a.id, patch)
  return (
    <li className="rounded-m3-md border border-outline-variant bg-surface-container-lowest p-3">
      <div className="flex items-start gap-2">
        <textarea
          aria-label="Action" rows={2} value={a.action} onChange={(e) => set({ action: e.target.value })}
          className={`min-w-0 flex-1 resize-none rounded-m3-xs border border-transparent bg-transparent px-1 py-0.5 md-body-medium hover:border-outline focus:border-primary focus:outline-none ${a.status === 'done' ? 'text-muted line-through' : 'text-on-surface'}`}
        />
        <IconButton icon="delete" label="Remove action" onClick={() => tracker.remove(lgd, a.id)} className="-mr-1 -mt-1 shrink-0" />
      </div>
      <div role="radiogroup" aria-label="Status" className="mt-2 flex flex-wrap gap-2">
        {STATUSES.map((s) => <Chip key={s} role="radio" aria-checked={a.status === s} selected={a.status === s} onClick={() => set({ status: s })}>{STATUS_LABEL[s]}</Chip>)}
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <SelectField label="Owner department" dense value={a.dept} onChange={(v) => set({ dept: v })} fieldBg="surface-container-lowest">
          <option value="">Not assigned</option>
          {DEPARTMENTS.map((d) => <option key={d.id} value={d.id}>{d.short}</option>)}
          {a.dept && !DEPARTMENTS.some((d) => d.id === a.dept) && <option value={a.dept}>{a.dept}</option>}
        </SelectField>
        <label className="md-field" style={{ '--md-field-bg': 'rgb(var(--md-rgb-surface-container-lowest))' } as React.CSSProperties}>
          <span className="md-field-label md-body-small">Due date</span>
          <input type="date" value={a.due} onChange={(e) => set({ due: e.target.value })} className="md-control md-control-dense md-body-medium" />
        </label>
      </div>
      <label className="md-field mt-4" style={{ '--md-field-bg': 'rgb(var(--md-rgb-surface-container-lowest))' } as React.CSSProperties}>
        <span className="md-field-label md-body-small">Note</span>
        <input value={a.note} onChange={(e) => set({ note: e.target.value })} placeholder="Add a note" className="md-control md-control-dense md-body-medium" />
      </label>
    </li>
  )
}

/** Action tracker (prototype, saved in this browser): actions grouped by district with status, owner department, due date and note. */
export default function TrackerSheet() {
  const { trackerOpen, setTrackerOpen, districts, byLgd, selected, myLgd } = useStore()
  const md = useMedia('(min-width: 768px)')
  const data = useTracker()
  const counts = trackerCounts(data)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ lgd: '', action: '', dept: '', due: '' })
  const sorted = useMemo(() => [...districts].sort((a, b) => a.state.localeCompare(b.state) || a.district.localeCompare(b.district)), [districts])
  const groups = useMemo(() => Object.entries(data)
    .map(([lgd, items]) => ({ lgd: Number(lgd), d: byLgd.get(Number(lgd)), items }))
    .sort((a, b) => (a.d?.state ?? '').localeCompare(b.d?.state ?? '') || (a.d?.district ?? '').localeCompare(b.d?.district ?? '')), [data, byLgd])

  const lgdVal = form.lgd || String(selected ?? myLgd ?? '')
  const submit = () => {
    const r = tracker.add(Number(lgdVal), { action: form.action, dept: form.dept, due: form.due })
    if (r) setForm({ lgd: lgdVal, action: '', dept: '', due: '' })
  }
  const download = () => {
    const csv = trackerCsv(data, (l) => byLgd.get(l), deptLabel)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    a.download = 'annadrishti_action_tracker.csv'
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  }

  return (
    <Sheet open={trackerOpen} onClose={() => setTrackerOpen(false)} side={md ? 'right' : 'bottom'} title="Action tracker" widthClass="max-w-xl">
      <div className={md ? '' : 'h-[75dvh]'}>
        <div className="space-y-3 px-4 pb-3">
          <p className="md-body-small text-muted">Prototype: saved in this browser only. {counts.total ? `${counts.total} tracked · ${counts.done} done.` : ''}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant={adding ? 'secondary' : 'primary'} onClick={() => setAdding(!adding)} aria-expanded={adding} iconLeft={<Icon name="add" size={18} />}>Add an action</Button>
            <Button size="sm" onClick={download} disabled={!counts.total} iconLeft={<Icon name="download" size={18} />}>Download (CSV)</Button>
          </div>
          {adding && (
            <form onSubmit={(e) => { e.preventDefault(); submit() }} className="space-y-4 rounded-m3-md bg-surface-container p-3 pt-4">
              <SelectField label="District" dense value={lgdVal} onChange={(v) => setForm({ ...form, lgd: v })} fieldBg="surface-container">
                <option value="">Choose a district</option>
                {sorted.map((d) => <option key={d.lgd} value={d.lgd}>{d.district}, {d.state}</option>)}
              </SelectField>
              <label className="md-field" style={{ '--md-field-bg': 'rgb(var(--md-rgb-surface-container))' } as React.CSSProperties}>
                <span className="md-field-label md-body-small">Action</span>
                <input value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value })} placeholder="e.g. Move 400 t foodgrain to ration shops" className="md-control md-control-dense md-body-medium" />
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <SelectField label="Owner department" dense value={form.dept} onChange={(v) => setForm({ ...form, dept: v })} fieldBg="surface-container">
                  <option value="">Not assigned</option>
                  {DEPARTMENTS.map((d) => <option key={d.id} value={d.id}>{d.short}</option>)}
                </SelectField>
                <label className="md-field" style={{ '--md-field-bg': 'rgb(var(--md-rgb-surface-container))' } as React.CSSProperties}>
                  <span className="md-field-label md-body-small">Due date</span>
                  <input type="date" value={form.due} onChange={(e) => setForm({ ...form, due: e.target.value })} className="md-control md-control-dense md-body-medium" />
                </label>
              </div>
              <Button size="sm" variant="primary" type="submit" disabled={!lgdVal || !form.action.trim()}>Add to tracker</Button>
            </form>
          )}
        </div>
        {groups.length === 0 ? (
          <div className="px-6 py-10 text-center md-body-medium text-muted">
            <Icon name="checklist" size={40} className="mx-auto mb-2 text-outline" />
            No actions tracked yet. Add one above, or choose <b className="font-medium text-on-surface">Add to tracker</b> on a district&rsquo;s action list.
          </div>
        ) : (
          <div className="space-y-5 px-4 pb-6">
            {groups.map((g) => {
              const done = g.items.filter((x) => x.status === 'done').length
              return (
                <section key={g.lgd} aria-label={g.d?.district ?? `District ${g.lgd}`}>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <h3 className="md-title-medium">{g.d?.district ?? `District ${g.lgd}`}<span className="ml-2 md-body-small font-normal text-muted">{g.d?.state}</span></h3>
                    <Pill tone={done === g.items.length ? 'accent' : 'muted'}>{done} of {g.items.length} done</Pill>
                  </div>
                  <ul className="space-y-2">{g.items.map((a) => <Row key={a.id} lgd={g.lgd} a={a} />)}</ul>
                </section>
              )
            })}
          </div>
        )}
      </div>
    </Sheet>
  )
}


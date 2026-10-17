import { useState } from 'react'
import { useStore } from '../lib/store'
import { useMedia } from '../lib/useMedia'
import { DEPARTMENTS } from '../lib/plain'
import type { Department } from '../types'
import { DistrictOfficerView, LegacyDrawer, hasOfficerView } from '../components/drawerBridge'
import GlanceTiles from '../components/GlanceTiles'
import LeftPanel from '../components/LeftPanel'
import MapView from '../components/MapView'
import Planner from '../components/Planner'
import { Button, Icon, IconButton, SelectField, Sheet } from '../components/ui'

function Panel({ lgd }: { lgd: number }) {
  const { byLgd, select, department, setDepartment, mode, year } = useStore()
  const d = byLgd.get(lgd)
  if (!hasOfficerView && LegacyDrawer) { const L = LegacyDrawer; return <div className="h-full [&>aside]:!w-full [&>aside]:!border-l-0"><L /></div> }
  return (
    <div className="flex h-full flex-col bg-surface">
      <div className="flex shrink-0 items-center gap-2 border-b border-outline-variant bg-surface px-3 py-2">
        <span className="min-w-0 flex-1 truncate md-title-small text-muted">{d?.district} · department view</span>
        <SelectField label="Department" hideLabel dense value={department} onChange={(v) => setDepartment(v as Department)} className="w-[180px] shrink-0">
          {DEPARTMENTS.map((x) => <option key={x.id} value={x.id}>{x.short}</option>)}
        </SelectField>
        <IconButton icon="close" label="Close" onClick={() => select(null)} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto"><DistrictOfficerView lgd={lgd} department={department} year={mode === 'history' ? year : undefined} /></div>
    </div>
  )
}

export default function PlannerRoute() {
  const { view, selected, select, mode } = useStore()
  const xl = useMedia('(min-width: 1280px)')
  const lg = useMedia('(min-width: 1024px)')
  const [layers, setLayers] = useState(false)
  const hist = mode === 'history'
  if (view === 'planner' && !hist) return <Planner />
  return (
    <>
      {!hist && <GlanceTiles />}
      <div className="flex min-h-0 flex-1">
        {xl && <LeftPanel className="w-[260px] shrink-0" />}
        <main className="relative min-w-0 flex-1">
          <MapView compact={!xl} />
          {!xl && <Button size="sm" className="absolute left-3 top-3 z-10 !bg-secondary-container shadow-elev-1" onClick={() => setLayers(true)} iconLeft={<Icon name="layers" size={18} />}>Map layers</Button>}
        </main>
        {lg && selected != null && <section className="w-[440px] shrink-0 border-l border-outline-variant" aria-label="District details"><Panel lgd={selected} /></section>}
      </div>
      <Sheet open={layers && !xl} onClose={() => setLayers(false)} side={lg ? 'right' : 'bottom'} title="Map layers" widthClass="max-w-xs">
        <LeftPanel className="border-0" onPick={() => setLayers(false)} />
      </Sheet>
      {!lg && <Sheet open={selected != null} onClose={() => select(null)} side="bottom" title="District details" widthClass=""><div className="h-[75dvh]">{selected != null && <Panel lgd={selected} />}</div></Sheet>}
    </>
  )
}

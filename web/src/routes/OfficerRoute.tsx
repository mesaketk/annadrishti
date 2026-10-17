import { useEffect, useState } from 'react'
import { useStore } from '../lib/store'
import { useMedia } from '../lib/useMedia'
import { DEPARTMENTS } from '../lib/plain'
import type { Department } from '../types'
import { DistrictOfficerView } from '../components/drawerBridge'
import DistrictPicker from '../components/DistrictPicker'
import LeftPanel from '../components/LeftPanel'
import MapView from '../components/MapView'
import { Button, Icon, SelectField, Sheet } from '../components/ui'

export default function OfficerRoute() {
  const { myLgd, setMyLgd, department, setDepartment, select, mode, year } = useStore()
  const xl = useMedia('(min-width: 1280px)')
  const md = useMedia('(min-width: 768px)')
  const [layers, setLayers] = useState(false)
  useEffect(() => { select(myLgd, myLgd != null) }, [myLgd, select])
  const view = myLgd != null
    ? <DistrictOfficerView lgd={myLgd} department={department} year={mode === 'history' ? year : undefined} />
    : <div className="grid place-items-center p-10 text-center md-body-large text-muted">Choose your district above, or tap it on the map.</div>
  const map = (
    <div className="relative h-full min-h-[220px]">
      <MapView compact={!xl} onSelect={(l) => setMyLgd(l)} />
      {!xl && <Button size="sm" className="absolute left-3 top-3 z-10 !bg-secondary-container shadow-elev-1" onClick={() => setLayers(true)} iconLeft={<Icon name="layers" size={18} />}>Map layers</Button>}
    </div>
  )
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-start gap-3 border-b border-outline-variant bg-surface px-3 pb-3 pt-4">
        <DistrictPicker value={myLgd} onChange={setMyLgd} className="min-w-[220px] flex-1 sm:max-w-sm" />
        <SelectField label="Department" value={department} onChange={(v) => setDepartment(v as Department)} className="min-w-[200px] flex-1 sm:max-w-sm">
          {DEPARTMENTS.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
        </SelectField>
      </div>
      {xl ? (
        <div className="flex min-h-0 flex-1">
          <LeftPanel hideSearch className="w-[260px] shrink-0" />
          <main className="min-w-0 flex-1">{map}</main>
          <section className="w-[480px] shrink-0 overflow-y-auto border-l border-outline-variant bg-surface" aria-label="District details">{view}</section>
        </div>
      ) : md ? (
        <div className="flex min-h-0 flex-1">
          <main className="w-[44%] shrink-0">{map}</main>
          <section className="min-w-0 flex-1 overflow-y-auto border-l border-outline-variant bg-surface" aria-label="District details" data-scroll-root>{view}</section>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto bg-surface" data-scroll-root>
          <div className="h-60">{map}</div>
          {view}
        </div>
      )}
      <Sheet open={layers && !xl} onClose={() => setLayers(false)} side={md ? 'right' : 'bottom'} title="Map layers" widthClass="max-w-xs">
        <LeftPanel hideSearch className="border-0" onPick={() => setLayers(false)} />
      </Sheet>
    </div>
  )
}

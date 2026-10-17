import { useStore } from '../lib/store'
import DistrictOfficerView from './drawer/DistrictOfficerView'

/** Thin transition wrapper: the officer view inside the existing drawer chrome. */
export default function DistrictDrawer() {
  const selected = useStore((s) => s.selected)
  const select = useStore((s) => s.select)
  if (selected == null) return null
  return (
    <aside className="flex h-full w-[440px] shrink-0 flex-col overflow-hidden border-l border-outline-variant bg-surface" aria-label="District details">
      <DistrictOfficerView lgd={selected} onClose={() => select(null)} />
    </aside>
  )
}

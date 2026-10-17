// Late-binds the drawer agent's components (components/drawer/index.ts[x]) so the shell builds before and after they land.
// Expected exports: DistrictFarmerView({lgd, language}), DistrictOfficerView({lgd, department, year?}).
import type { ComponentType } from 'react'
import { useStore } from '../lib/store'
import { useScenario } from '../lib/useScenario'
import { districtSentence } from '../lib/plain'
import type { Department, Lang } from '../types'
import { Card, TrafficLight } from './ui'

export interface FarmerViewProps { lgd: number; language: Lang; onLanguageChange?: (l: Lang) => void; year?: number }
export interface OfficerViewProps { lgd: number; department: Department; year?: number }

type Mod = { DistrictFarmerView?: ComponentType<FarmerViewProps>; DistrictOfficerView?: ComponentType<OfficerViewProps> }
const drawerMods = import.meta.glob('./drawer/index.{ts,tsx}', { eager: true }) as Record<string, Mod>
const legacyMods = import.meta.glob('./DistrictDrawer.tsx', { eager: true }) as Record<string, { default?: ComponentType }>
const m: Mod = Object.values(drawerMods)[0] ?? {}
export const LegacyDrawer: ComponentType | null = Object.values(legacyMods)[0]?.default ?? null
export const hasOfficerView = !!m.DistrictOfficerView

function Placeholder({ lgd, who }: { lgd: number; who: string }) {
  const d = useStore((s) => s.byLgd.get(lgd))
  const kpis = useStore((s) => s.kpis)
  const { key } = useScenario()
  if (!d) return null
  return (
    <Card className="m-3" title={`${d.district}, ${d.state}`} right={<TrafficLight band={d.risk[key(d)]?.band} />}>
      <p className="md-body text-on-surface">{districtSentence(d, key(d), kpis)}</p>
      <p className="mt-2 md-body text-muted">{who} view is loading from the district module.</p>
    </Card>
  )
}
export const DistrictFarmerView: ComponentType<FarmerViewProps> = m.DistrictFarmerView ?? (({ lgd }) => <Placeholder lgd={lgd} who="Farmer" />)
export const DistrictOfficerView: ComponentType<OfficerViewProps> = m.DistrictOfficerView ?? (({ lgd }) => <Placeholder lgd={lgd} who="Officer" />)

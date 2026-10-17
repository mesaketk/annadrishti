import { useEffect, useMemo, useState } from 'react'
import { riskAt } from '../../lib/scenario'
import { useScenario } from '../../lib/useScenario'
import { useStore } from '../../lib/store'
import type { Department } from '../../types'
import { DepartmentBriefing } from '../advisory'
import PrepositionCard from './Actions'
import OverviewTab from './OverviewTab'
import { driversOf, headline, outlookPhrase, seasonName, seasonWhen } from './copy'
import { OfficerTrends } from './TrendsTab'
import { FullBreakdown, TopDrivers } from './Why'
import { Card, Skeleton, TabPanel, Tabs, TrafficLight } from './ui'
import { IconButton } from '../ui'
import type { TabDef } from './ui'
import { useTimeseries } from './useTimeseries'

type TabId = 'overview' | 'why' | 'trends' | 'actions'
const TABS: TabDef<TabId>[] = [
  { id: 'overview', label: 'Overview' }, { id: 'why', label: 'Why' }, { id: 'trends', label: 'Trends' }, { id: 'actions', label: 'Actions' },
]

export interface DistrictOfficerViewProps {
  lgd: number
  /** Fixes the briefing department (no selector). */
  department?: Department
  /** Highlights this year on the Trends charts (and opens the Trends tab). */
  year?: number
  /** Shows a close button in the header. */
  onClose?: () => void
}

export default function DistrictOfficerView({ lgd, department, year, onClose }: DistrictOfficerViewProps) {
  const d = useStore((s) => s.byLgd.get(lgd))
  const kpis = useStore((s) => s.kpis)
  const sc = useScenario()
  const [tab, setTab] = useState<TabId>(year != null ? 'trends' : 'overview')
  useEffect(() => { setTab(year != null ? 'trends' : 'overview') }, [lgd, year])
  const ts = useTimeseries(lgd, tab === 'trends')
  const scenarioKey = d ? sc.key(d) : 'elnino'
  const r = d ? riskAt(d, scenarioKey) : null
  const status = sc.seasonObj?.status ?? null
  const when = seasonWhen(sc.season, status, d?.main_season)
  const ensoState = kpis?.outlook?.enso?.state ?? kpis?.enso?.state
  const outlook = outlookPhrase(sc.phase, ensoState)
  const drivers = useMemo(() => (d ? driversOf(d, r) : []), [d, r])
  const sentence = d ? headline({ band: r?.band, drivers, when, outlook }) : ''
  const seasonShort = seasonName(sc.season, d?.main_season)
  const rabi = /rabi/i.test(sc.season ?? '') || (!sc.season && d?.main_season === 'OND')

  if (!d) {
    return <div className="p-4"><Skeleton className="h-8 w-1/2" /><Skeleton className="mt-3 h-20 w-full" /></div>
  }
  const idp = `dov-${lgd}`
  return (
    <div className="flex h-full min-h-0 flex-col bg-surface text-on-surface">
      <header className="shrink-0 bg-surface px-4 pb-3 pt-4">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="truncate md-headline-small">{d.district}</h2>
            <p className="md-body text-muted">{d.state}{sc.seasonObj ? ` · ${sc.seasonObj.label}` : seasonShort ? ` · ${seasonShort}` : ''}</p>
          </div>
          <TrafficLight band={r?.band} size="lg" />
          {onClose && <IconButton icon="close" label="Close district details" onClick={onClose} className="-mr-1" />}
        </div>
        <p className="mt-3 md-body text-on-surface" data-testid="headline">{sentence}</p>
      </header>
      <Tabs tabs={TABS} value={tab} onChange={setTab} idPrefix={idp} label="District details" />
      <div className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-4" key={lgd}>
        <TabPanel id="overview" idPrefix={idp} active={tab === 'overview'}>
          <OverviewTab d={d} r={r} scenarioKey={scenarioKey} seasonId={sc.season} seasonLabel={sc.seasonObj?.label ?? null} outlook={outlook} />
        </TabPanel>
        <TabPanel id="why" idPrefix={idp} active={tab === 'why'} className="space-y-3">
          <Card title="The three biggest reasons"><TopDrivers d={d} r={r} n={3} /></Card>
          <FullBreakdown d={d} r={r} scenarioKey={scenarioKey} rabi={rabi} />
        </TabPanel>
        <TabPanel id="trends" idPrefix={idp} active={tab === 'trends'}>
          <OfficerTrends d={d} s={ts} year={year} />
        </TabPanel>
        <TabPanel id="actions" idPrefix={idp} active={tab === 'actions'} className="space-y-3">
          <PrepositionCard d={d} r={r} scenarioKey={scenarioKey} seasonId={sc.season} seasonLabel={sc.seasonObj?.label ?? null} />
          <DepartmentBriefing d={d} scenarioKey={scenarioKey} department={department} />
        </TabPanel>
      </div>
    </div>
  )
}

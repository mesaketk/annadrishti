import { useEffect, useState } from 'react'
import { riskAt } from '../../lib/scenario'
import { useScenario } from '../../lib/useScenario'
import { useStore } from '../../lib/store'
import type { Lang } from '../../types'
import { FarmerAdvice, HelpList } from '../advisory'
import { lightOf, seasonName } from './copy'
import { t } from './i18n'
import { FarmerTrends } from './TrendsTab'
import { PastElNinoSentence, TopDrivers } from './Why'
import { Card, Skeleton, TabPanel, Tabs, TrafficLight } from './ui'
import type { TabDef } from './ui'
import { useTimeseries } from './useTimeseries'

type TabId = 'advice' | 'why' | 'trends'

export interface DistrictFarmerViewProps {
  lgd: number
  language: Lang
  /** Called when the farmer picks another language in the Advice tab. */
  onLanguageChange?: (l: Lang) => void
  /** Highlights this year on the Trends charts (and opens the Trends tab). */
  year?: number
}

export default function DistrictFarmerView({ lgd, language, onLanguageChange, year }: DistrictFarmerViewProps) {
  const d = useStore((s) => s.byLgd.get(lgd))
  const sc = useScenario()
  const [lang, setLang] = useState<Lang>(language)
  useEffect(() => setLang(language), [language])
  const pick = (l: Lang) => { setLang(l); onLanguageChange?.(l) }
  const [tab, setTab] = useState<TabId>(year != null ? 'trends' : 'advice')
  useEffect(() => { setTab(year != null ? 'trends' : 'advice') }, [lgd, year])
  const ts = useTimeseries(lgd, tab === 'trends')

  if (!d) return <div className="p-4"><Skeleton className="h-10 w-2/3" /><Skeleton className="mt-3 h-40 w-full" /></div>
  const scenarioKey = sc.key(d)
  const r = riskAt(d, scenarioKey)
  const light = lightOf(r?.band)
  const sName = seasonName(sc.season, d.main_season)
  const seasonText = sName
    ? t(lang, sc.seasonObj?.status === 'upcoming' ? 'season.next' : 'season.this', { season: t(lang, `season.${sName.toLowerCase()}`) })
    : t(lang, 'season.none')
  const tabs: TabDef<TabId>[] = [
    { id: 'advice', label: t(lang, 'tab.advice'), icon: 'grass' }, { id: 'why', label: t(lang, 'tab.why'), icon: 'help' }, { id: 'trends', label: t(lang, 'tab.trends'), icon: 'trending_up' },
  ]
  const idp = `dfv-${lgd}`
  return (
    <div className="relative flex min-h-full flex-col bg-surface text-on-surface" lang={lang}>
      <header className="sticky top-0 z-20 border-b border-outline-variant bg-surface px-4 py-3">
        <div className="mx-auto w-full max-w-xl">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate md-headline-small">{d.district}</h2>
            <p className="truncate md-body text-muted">{d.state} · {seasonText}</p>
          </div>
          <TrafficLight band={r?.band} size="md" label={t(lang, `light.${light.key}`)} />
        </div>
        <p className="mt-2 md-body font-medium">{t(lang, `light.${light.key}.say`)}</p>
        </div>
      </header>

      <div className="mx-auto w-full max-w-xl flex-1 space-y-4 p-4 pb-6">
        <TabPanel id="advice" idPrefix={idp} active={tab === 'advice'} className="space-y-4">
          <FarmerAdvice key={lgd} d={d} scenarioKey={scenarioKey} lang={lang} onLanguageChange={pick} />
          <HelpList lang={lang} />
        </TabPanel>
        <TabPanel id="why" idPrefix={idp} active={tab === 'why'} className="space-y-4">
          <Card title={t(lang, 'why.title')}><div><TopDrivers d={d} r={r} n={3} lang={lang} /></div></Card>
          <PastElNinoSentence d={d} lang={lang} />
        </TabPanel>
        <TabPanel id="trends" idPrefix={idp} active={tab === 'trends'}>
          <FarmerTrends d={d} s={ts} lang={lang} year={year} />
        </TabPanel>
      </div>

      <nav className="fixed inset-x-0 bottom-0 z-20 bg-surface-container" aria-label={t(lang, 'tab.advice')}>
        <div className="mx-auto w-full max-w-xl">
        <Tabs tabs={tabs} value={tab} onChange={setTab} idPrefix={idp} variant="bottom" label={d.district} />
        </div>
      </nav>
    </div>
  )
}

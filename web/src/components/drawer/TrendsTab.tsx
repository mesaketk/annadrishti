import type { District, Lang } from '../../types'
import { NutritionMultiples, PdsChart, PoshanChart, PriceChart, RainChart, YieldChart, useYearNote } from './charts'
import { t } from './i18n'
import { Card, ErrorNote, Skeleton } from './ui'
import type { TsState } from './useTimeseries'

function Loading() {
  return <div className="space-y-3" aria-busy="true"><Skeleton className="h-60 w-full" /><Skeleton className="h-52 w-full" /><Skeleton className="h-52 w-full" /></div>
}

export function OfficerTrends({ d, s, year }: { d: District; s: TsState; year?: number }) {
  const note = useYearNote(d, s.ts, year)
  if (s.loading && !s.ts) return <Loading />
  if (s.error && !s.noHistory) return <ErrorNote onRetry={s.retry}>Year-by-year history could not be loaded: {s.error}</ErrorNote>
  return (
    <div className="space-y-3">
      {note && <div className="rounded-m3-md bg-primary-container px-4 py-3 md-title-small text-on-primary-container" role="status">{note}</div>}
      {s.noHistory && <Card><p className="md-body text-muted">Year-by-year history for yield, ration-shop grain and the like is not available in demo mode. Charts that come from the district file are shown below.</p></Card>}
      {s.ts && <YieldChart d={d} ts={s.ts} year={year} />}
      <RainChart d={d} ts={s.ts} year={year} />
      <NutritionMultiples d={d} ts={s.ts} />
      <PoshanChart d={d} />
      <PdsChart ts={s.ts} />
      <PriceChart d={d} />
    </div>
  )
}

export function FarmerTrends({ d, s, lang, year }: { d: District; s: TsState; lang: Lang; year?: number }) {
  const note = useYearNote(d, s.ts, year)
  if (s.loading && !s.ts) return <Loading />
  if (s.error && !s.noHistory) return <ErrorNote onRetry={s.retry}>{t(lang, 'trends.none')}</ErrorNote>
  return (
    <div className="space-y-4">
      {note && <div className="rounded-m3-lg bg-primary-container px-4 py-3 md-title-medium text-on-primary-container" role="status">{note}</div>}
      {s.ts ? <YieldChart d={d} ts={s.ts} year={year} lang={lang} /> : <Card><p className="md-body text-muted">{t(lang, 'trends.none')}</p></Card>}
      <RainChart d={d} ts={s.ts} year={year} lang={lang} />
    </div>
  )
}

import { useEffect } from 'react'
import { useStore } from '../lib/store'
import { HIST_MAX, HIST_MIN, prefetchHistory, resetHistoryCache, useHistoryIndex } from '../lib/history'
import { useState } from 'react'
import { Button, Icon, Pill, Skeleton } from './ui'
import type { Tone } from '../lib/plain'

export const phaseTone = (p?: string): Tone => (/el ni/i.test(p ?? '') ? 'act' : /la ni/i.test(p ?? '') ? 'info' : 'muted')

/** Year slider + play/pause + ENSO chip and headline for the selected year (History mode). */
export default function HistoryBar() {
  const { year, setYear, playing, setPlaying, historyLayer } = useStore()
  const [nonce, setNonce] = useState(0)
  const idx = useHistoryIndex(true, nonce)
  const years = idx.data?.years?.length ? idx.data.years : null
  const min = years ? Math.min(...years) : HIST_MIN
  const max = years ? Math.max(...years) : HIST_MAX
  const e = idx.data?.enso?.[String(year)]

  useEffect(() => { if (year < min || year > max) setYear(Math.min(max, Math.max(min, year))) }, [min, max]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!playing || idx.error) return
    prefetchHistory([year + 1, year + 2])
    const t = setTimeout(() => setYear(year >= max ? min : year + 1), 1600)
    return () => clearTimeout(t)
  }, [playing, year, min, max, setYear, idx.error])

  if (idx.error) {
    return (
      <div className="flex flex-wrap items-center gap-3 border-t border-outline-variant bg-surface-container-low px-4 py-2 md-body-medium" role="status">
        <b className="font-medium">History not available yet.</b>
        <span className="text-muted">The past-years data is still being prepared.</span>
        <Button size="sm" onClick={() => { resetHistoryCache(); setNonce(nonce + 1) }}>Check again</Button>
      </div>
    )
  }
  return (
    <div className="border-t border-outline-variant bg-surface-container-low px-3 py-2 sm:px-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <div className="flex min-w-[260px] flex-1 items-center gap-2">
          <Button variant="primary" size="md" onClick={() => setPlaying(!playing)} aria-label={playing ? 'Pause' : 'Play through the years'} className="w-12 shrink-0 !px-0"><Icon name={playing ? 'pause' : 'play_arrow'} fill size={28} /></Button>
          <span className="w-16 shrink-0 md-headline-small tabular-nums" aria-live="polite">{year}</span>
          <input
            type="range" className="slider min-w-0 flex-1" min={min} max={max} step={1} value={year} aria-label="Year" style={{ '--p': `${max > min ? ((year - min) / (max - min)) * 100 : 0}%` } as React.CSSProperties}
            onChange={(ev) => { setPlaying(false); setYear(Number(ev.target.value)); prefetchHistory([Number(ev.target.value) + 1]) }}
          />
        </div>
        <div className="flex min-w-0 flex-[2] basis-full flex-wrap items-center gap-2 md:basis-0 md:flex-nowrap" data-testid="history-headline">
          {idx.loading && !idx.data ? <Skeleton className="h-5 w-64" /> : (
            <>
              {e?.phase && <Pill tone={phaseTone(e.phase)} size="md" dot>{e.phase}</Pill>}
              <span className="min-w-0 md-body-medium">
                {e?.headline ?? 'No summary for this year.'}
                {historyLayer === 'h_hit' && e?.n_loss_districts ? <b className="ml-1 font-medium text-primary">Warned in {e.n_loss_warned ?? 0} of {e.n_loss_districts} districts where the harvest fell ({Math.round(e.pct_loss_warned ?? ((e.n_loss_warned ?? 0) / e.n_loss_districts) * 100)} %).</b> : null}
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from '../lib/store'
import { useScenario } from '../lib/useScenario'
import { tr } from '../lib/plain'
import type { Lang } from '../types'
import { Button, Icon, TrafficLight } from './ui'

const label = (d: { district: string; state: string }) => `${d.district}, ${d.state}`
const size20 = (big: boolean) => (big ? 24 : 20)

/** Search box (district or state) with an optional "Use my location" button (nearest district centroid). */
export default function DistrictPicker({ value, onChange, lang = 'en', locate = false, locateIcon = false, big = false, className = '' }: {
  value: number | null; onChange: (lgd: number) => void; lang?: Lang; locate?: boolean; locateIcon?: boolean; big?: boolean; className?: string
}) {
  const districts = useStore((s) => s.districts)
  const byLgd = useStore((s) => s.byLgd)
  const { key } = useScenario()
  const cur = value != null ? byLgd.get(value) : undefined
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => { setText(cur ? label(cur) : '') }, [cur?.lgd]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const h = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const results = useMemo(() => {
    const s = text.trim().toLowerCase()
    if (!s || (cur && text === label(cur))) return []
    const score = (d: { district: string; state: string }) => (d.district.toLowerCase().startsWith(s) ? 0 : d.district.toLowerCase().includes(s) ? 1 : d.state.toLowerCase().includes(s) ? 2 : 9)
    return districts.map((d) => [score(d), d] as const).filter(([k]) => k < 9).sort((a, b) => a[0] - b[0] || a[1].district.localeCompare(b[1].district)).slice(0, 8).map(([, d]) => d)
  }, [text, districts, cur])

  const pick = (lgd: number) => { onChange(lgd); setOpen(false); setMsg(null) }
  const useLocation = () => {
    if (!navigator.geolocation) { setMsg(tr(lang, 'locfail')); return }
    setBusy(true); setMsg(null)
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setBusy(false)
        const { latitude: la, longitude: lo } = p.coords
        let best: { lgd: number; dd: number } | null = null
        for (const d of districts) {
          if (!d.centroid) continue
          const dy = d.centroid[1] - la, dx = (d.centroid[0] - lo) * Math.cos((la * Math.PI) / 180)
          const dd = dx * dx + dy * dy
          if (!best || dd < best.dd) best = { lgd: d.lgd, dd }
        }
        if (best) { pick(best.lgd); setMsg(tr(lang, 'located')) } else setMsg(tr(lang, 'locfail'))
      },
      () => { setBusy(false); setMsg(tr(lang, 'locfail')) },
      { timeout: 10000, maximumAge: 600000 },
    )
  }

  return (
    <div ref={root} className={className}>
      <div className="flex items-start gap-2">
      <div className="relative min-w-0 flex-1">
        <label className="md-field">
          <span className="md-field-label md-body-small">{tr(lang, 'home')}</span>
          <input
            value={text} onChange={(e) => { setText(e.target.value); setOpen(true) }} onFocus={(e) => { e.target.select(); setOpen(true) }}
            placeholder={tr(lang, 'search')} aria-label={tr(lang, 'pick')} autoComplete="off" role="combobox" aria-expanded={open && results.length > 0} aria-autocomplete="list"
            className={`md-control md-body-large ${big ? 'min-h-[56px]' : ''}`}
          />
        </label>
        {open && results.length > 0 && (
          <ul role="listbox" className="absolute z-40 mt-1 max-h-72 w-full overflow-auto rounded-m3-xs bg-surface-container py-2 shadow-elev-2">
            {results.map((d) => (
              <li key={d.lgd} role="option" aria-selected={d.lgd === value}>
                <button type="button" onClick={() => pick(d.lgd)} className="md-state flex min-h-[56px] w-full items-center justify-between gap-2 px-4 py-1.5 text-left">
                  <span><b className="md-title-small">{d.district}</b><br /><span className="md-body-medium text-muted">{d.state}</span></span>
                  <TrafficLight band={d.risk[key(d)]?.band} variant="dot" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {locateIcon && (
        <Button variant="secondary" size={big ? 'lg' : 'md'} loading={busy} onClick={useLocation} aria-label={tr(lang, 'locate')} title={tr(lang, 'locate')} className="shrink-0 !px-0 w-12 sm:w-14"><Icon name="my_location" size={24} /></Button>
      )}
      </div>
      {locate && (
        <div className="mt-2">
          <Button variant="secondary" size={big ? 'lg' : 'md'} block loading={busy} onClick={useLocation} iconLeft={<Icon name="my_location" size={size20(big)} />}>{tr(lang, 'locate')}</Button>
        </div>
      )}
      {msg && <p className="mt-2 md-body-medium text-muted" role="status">{msg}</p>}
    </div>
  )
}

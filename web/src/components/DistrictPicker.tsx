import { useState } from 'react'
import { useStore } from '../lib/store'
import { tr } from '../lib/plain'
import type { Lang } from '../types'
import { Button, Icon } from './ui'
import DistrictCombobox from './DistrictCombobox'

const size20 = (big: boolean) => (big ? 24 : 20)

/** Search box (district or state) with an optional "Use my location" button (nearest district centroid). */
export default function DistrictPicker({ value, onChange, lang = 'en', locate = false, locateIcon = false, big = false, className = '' }: {
  value: number | null; onChange: (lgd: number) => void; lang?: Lang; locate?: boolean; locateIcon?: boolean; big?: boolean; className?: string
}) {
  const districts = useStore((s) => s.districts)
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const pick = (lgd: number) => { onChange(lgd); setMsg(null) }
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
    <div className={className}>
      <div className="flex items-start gap-2">
      <DistrictCombobox className="min-w-0 flex-1" value={value} onPick={pick} lang={lang} big={big} />
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

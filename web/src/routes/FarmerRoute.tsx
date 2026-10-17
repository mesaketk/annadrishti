import { useEffect, useState } from 'react'
import { useStore } from '../lib/store'
import { LANGS, tr } from '../lib/plain'
import { DistrictFarmerView } from '../components/drawerBridge'
import DistrictPicker from '../components/DistrictPicker'
import type { Lang } from '../types'
import { Chip } from '../components/ui'

function LangChips({ value, onChange }: { value: Lang; onChange: (l: Lang) => void }) {
  return (
    <div role="radiogroup" aria-label={tr(value, 'language')} className="hide-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 py-2">
      {LANGS.map((l) => (
        <Chip key={l.id} size="lg" role="radio" aria-checked={l.id === value} selected={l.id === value} lang={l.id} onClick={() => onChange(l.id)} title={l.english}>{l.native}</Chip>
      ))}
    </div>
  )
}

/**
 * Mobile-first farmer page: pick district (search or GPS) and language, then the drawer's farmer view, which carries
 * its own sticky district header + traffic light and its bottom tab bar (Advice / Why / Trends).
 */
export default function FarmerRoute() {
  const { myLgd, setMyLgd, language, setLanguage, byLgd } = useStore()
  const d = myLgd != null ? byLgd.get(myLgd) : undefined
  const [first, setFirst] = useState(!d)
  useEffect(() => { if (d) setFirst(false) }, [d])

  return (
    <div className="farmer min-h-0 flex-1 overflow-y-auto" data-scroll-root>
      <div className="mx-auto flex min-h-full max-w-xl flex-col">
        <section className="relative z-0 space-y-3 px-4 pb-4 pt-4" aria-label={tr(language, 'pick')}>
          {first || !d ? (
            <>
              <h1 className="md-headline-small">{tr(language, 'pick')}</h1>
              <DistrictPicker big lang={language} locate value={myLgd} onChange={setMyLgd} />
            </>
          ) : (
            <DistrictPicker lang={language} locateIcon value={myLgd} onChange={setMyLgd} />
          )}
          {(first || !d) && <LangChips value={language} onChange={setLanguage} />}
        </section>
        {d ? (
          <div className="flex-1"><DistrictFarmerView lgd={d.lgd} language={language} onLanguageChange={setLanguage} /></div>
        ) : <div className="flex-1" />}
        <p className="bg-surface px-4 pb-28 pt-4 md-body-small text-muted">Scenarios built from past years, not exact forecasts. Ask your local agriculture office (KVK) before big decisions.</p>
      </div>
    </div>
  )
}

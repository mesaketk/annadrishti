import { useEffect, useRef, useState } from 'react'
import { useStore, type View } from '../lib/store'
import { useRoute } from '../lib/route'
import { useMedia } from '../lib/useMedia'
import { PHASES, availablePhases, seasonsOf } from '../lib/scenario'
import { LANGS, PHASE_PLAIN } from '../lib/plain'
import type { Lang, PhaseId } from '../types'
import { Button, Icon, IconButton, Pill, Segmented, SelectField, Sheet } from './ui'
import { ROLE_INFO, chooseRole } from './RolePicker'
import HistoryBar from './HistoryBar'

function Logo() {
  return (
    <svg width="40" height="40" viewBox="0 0 32 32" aria-hidden className="shrink-0">
      <rect width="32" height="32" rx="10" className="fill-primary" />
      <path d="M16 6c-1 5-6 6-6 11a6 6 0 0 0 12 0c0-5-5-6-6-11z" className="fill-on-primary" />
      <path d="M16 13v10M16 18l-3-2.5M16 20l3-2.5" className="stroke-primary" strokeWidth="1.4" strokeLinecap="round" fill="none" />
    </svg>
  )
}

const STATUS: Record<string, string> = { sowing_now: 'sowing now', upcoming: 'coming up' }

/** "El Niño likely (61 %)" for the selected season, from kpis.outlook. */
function useOutlookSentence() {
  const { kpis, season } = useStore()
  const seasons = seasonsOf(kpis)
  const sObj = seasons.find((x) => x.id === season)
  const probs = season ? kpis?.outlook?.enso?.p_by_season?.[season] : undefined
  let outlook: string | null = null
  if (probs) {
    const names = { elnino: 'El Niño', neutral: 'Normal conditions', lanina: 'La Niña' } as const
    const [k, p] = (Object.entries(probs) as [keyof typeof names, number][]).sort((a, b) => b[1] - a[1])[0] ?? []
    if (k && p != null) outlook = `${names[k]} likely (${Math.round(p * 100)} %)`
  } else if (kpis?.enso?.state) outlook = `${kpis.enso.state} now`
  const seasonText = sObj ? `${sObj.label}${sObj.status && STATUS[sObj.status] ? ` (${STATUS[sObj.status]})` : ''}` : null
  return { seasonText, outlook }
}

/** Season (segmented button) and "what if the weather is…" (segmented on wide screens, outlined select otherwise). */
export function Controls({ stacked = false }: { stacked?: boolean }) {
  const { kpis, districts, season, setSeason, phase, setPhase } = useStore()
  const xl = useMedia('(min-width: 1280px)')
  const seasons = seasonsOf(kpis)
  const phases = PHASES.filter((p) => availablePhases(districts, season).includes(p.id))
  const phaseVal = phases.some((p) => p.id === phase) ? phase : phases[0]?.id
  const optLabel = (s: { label: string; status?: string | null }) => `${s.label}${s.status && STATUS[s.status] ? ` (${STATUS[s.status]})` : ''}`
  return (
    <div className={stacked ? 'space-y-6 p-4' : 'flex flex-wrap items-center gap-3'}>
      {seasons.length > 0 && season && (
        <div className={stacked ? 'block' : 'flex items-center gap-2'}>
          <span className={stacked ? 'mb-2 block md-label-large' : 'md-body-medium text-muted'}>Season</span>
          {seasons.length <= 3
            ? <Segmented value={season} onChange={setSeason} options={seasons.map((s) => ({ id: s.id, label: s.label, title: optLabel(s) }))} />
            : <SelectField label="Season" hideLabel dense value={season} onChange={setSeason} fieldBg="surface-container-low">{seasons.map((s) => <option key={s.id} value={s.id}>{optLabel(s)}</option>)}</SelectField>}
        </div>
      )}
      {phaseVal && (
        <div className={stacked ? 'block' : 'flex items-center gap-2'}>
          <span className={stacked ? 'mb-2 block md-label-large' : 'md-body-medium text-muted'}>What if the weather is…</span>
          {xl && !stacked
            ? <Segmented<PhaseId> value={phaseVal} onChange={setPhase} options={phases.map((p) => ({ id: p.id, label: PHASE_PLAIN[p.id], title: p.label }))} />
            : <SelectField label="What if the weather is…" hideLabel dense={!stacked} value={phaseVal} onChange={(v) => setPhase(v as PhaseId)} fieldBg="surface-container-low" className={stacked ? 'w-full' : ''}>{phases.map((p) => <option key={p.id} value={p.id}>{PHASE_PLAIN[p.id]}</option>)}</SelectField>}
        </div>
      )}
    </div>
  )
}

function RoleMenu() {
  const role = useStore((s) => s.role)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const h = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const r = role ?? 'planner'
  const none = role == null
  return (
    <div ref={ref} className="relative">
      <Button variant="secondary" size="sm" onClick={() => setOpen(!open)} aria-haspopup="menu" aria-expanded={open} title="Switch role" iconLeft={<Icon name={ROLE_INFO[r].icon} size={20} />} className="!px-3 sm:!px-4">
        <span className="hidden sm:inline">{none ? 'Pick a role' : ROLE_INFO[r].title}</span><Icon name="expand_more" size={20} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </Button>
      {open && (
        <div role="menu" className="absolute right-0 z-50 mt-1 w-64 rounded-m3-xs bg-surface-container py-2 shadow-elev-2">
          <div className="px-4 py-2 md-label-medium text-muted">I am a…</div>
          {(Object.keys(ROLE_INFO) as (keyof typeof ROLE_INFO)[]).map((k) => (
            <button key={k} role="menuitemradio" aria-checked={k === role} onClick={() => { chooseRole(k); setOpen(false) }}
              className={`md-state flex h-12 w-full items-center gap-3 px-3 text-left md-label-large ${k === role ? 'bg-secondary-container text-on-secondary-container' : 'text-on-surface'}`}>
              <Icon name={ROLE_INFO[k].icon} size={22} fill={k === role} />{ROLE_INFO[k].title}{k === role && <Icon name="check" size={20} className="ml-auto" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Header({ onMethods }: { onMethods: () => void }) {
  const route = useRoute()
  const { mock, mode, setMode, view, setView, language, setLanguage } = useStore()
  const { seasonText, outlook } = useOutlookSentence()
  const [sheet, setSheet] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const farmer = route === 'farmer'
  const canHistory = route === 'officer' || route === 'planner'
  const hist = canHistory && mode === 'history'

  // M3 "scrim on scroll": the app bar picks up the surface-container tone + elevation once page content scrolls under it.
  useEffect(() => {
    const h = (e: Event) => {
      const t = e.target as HTMLElement | null
      if (t && t.nodeType === 1 && t.hasAttribute('data-scroll-root')) setScrolled(t.scrollTop > 2)
    }
    document.addEventListener('scroll', h, { capture: true, passive: true })
    return () => document.removeEventListener('scroll', h, { capture: true })
  }, [])
  useEffect(() => { setScrolled(false) }, [route])

  return (
    <header className={`sticky top-0 z-30 shrink-0 transition-[background-color,box-shadow] duration-200 ${scrolled ? 'bg-surface-container shadow-elev-1' : 'bg-surface'}`}>
      <div className="flex min-h-[64px] items-center gap-2 px-3 sm:gap-3 sm:px-4">
        <div className="flex min-w-0 items-center gap-3">
          <Logo />
          <div className="min-w-0">
            <div className="truncate md-title-medium sm:md-title-large text-on-surface">AnnaDrishti <span className="hidden text-on-surface-variant sm:inline">अन्नदृष्टि</span></div>
            <div className="hidden truncate md-body-small text-on-surface-variant lg:block">Early warning for food and farming in India</div>
          </div>
        </div>

        {route === 'planner' && !hist && (
          <div className="ml-2 hidden md:block">
            <Segmented<View> value={view} onChange={setView} options={[{ id: 'map', label: 'Map' }, { id: 'planner', label: 'What to prepare' }]} />
          </div>
        )}
        {canHistory && (
          <div className="ml-1 hidden sm:block">
            <Segmented<'now' | 'history'> value={mode} onChange={setMode} options={[{ id: 'now', label: 'Now', title: 'Current season outlook' }, { id: 'history', label: 'History', title: 'What happened in past years, 2003 to 2024' }]} />
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          {mock && <Pill tone="watch" className="hidden sm:inline-flex" title="API unreachable: showing generated demo data">demo data</Pill>}
          {!farmer && <SelectField label="Language" hideLabel dense id="hdr-lang" value={language} onChange={(v) => setLanguage(v as Lang)} className="hidden w-[136px] sm:block">
            {LANGS.map((l) => <option key={l.id} value={l.id}>{l.native}</option>)}
          </SelectField>}
          {!farmer && (
            <label className="md-state md-hit relative inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-on-surface-variant has-[:focus-visible]:outline has-[:focus-visible]:outline-[3px] has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-secondary sm:hidden" title="Language">
              <Icon name="language" />
              <select aria-label="Language" value={language} onChange={(e) => setLanguage(e.target.value as Lang)} className="absolute inset-0 h-full w-full cursor-pointer opacity-0">
                {LANGS.map((l) => <option key={l.id} value={l.id}>{l.native}</option>)}
              </select>
            </label>
          )}
          <RoleMenu />
          <Button variant="ghost" size="sm" onClick={onMethods} aria-haspopup="dialog" className="hidden md:inline-flex">Data &amp; methods</Button>
          <IconButton icon="info" label="Data and methods" onClick={onMethods} aria-haspopup="dialog" className="md:hidden" />
        </div>
      </div>

      {canHistory && (
        <div className="flex flex-wrap items-center gap-2 px-3 pb-2 sm:hidden">
          <Segmented<'now' | 'history'> value={mode} onChange={setMode} options={[{ id: 'now', label: 'Now' }, { id: 'history', label: 'History' }]} />
          {route === 'planner' && !hist && <Segmented<View> value={view} onChange={setView} options={[{ id: 'map', label: 'Map' }, { id: 'planner', label: 'What to prepare' }]} />}
        </div>
      )}

      {hist ? (
        <HistoryBar />
      ) : (
        <div className="flex items-center gap-x-4 gap-y-1 border-t border-outline-variant bg-surface-container-low px-3 py-2 sm:px-4">
          <p className="min-w-0 flex-1 md-body-medium" data-testid="context-line">
            {seasonText && <><span className="text-muted">Season:</span> <b className="font-medium">{seasonText}</b></>}
            {seasonText && outlook && <span className="text-muted"> · </span>}
            {outlook && <><span className="text-muted">Outlook:</span> <b className="font-medium">{outlook}</b></>}
          </p>
          {!farmer && (
            <>
              <div className="hidden md:block"><Controls /></div>
              <Button size="sm" variant="secondary" className="md:hidden" onClick={() => setSheet(true)}>Change</Button>
            </>
          )}
        </div>
      )}
      <Sheet open={sheet} onClose={() => setSheet(false)} side="bottom" title="Season and outlook"><Controls stacked /></Sheet>
    </header>
  )
}

import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import { useStore } from '../lib/store'
import { useScenario } from '../lib/useScenario'
import { useMedia } from '../lib/useMedia'
import { tr } from '../lib/plain'
import type { District, Lang } from '../types'
import { Sheet, TrafficLight, cx } from './ui'

export const districtLabel = (d: { district: string; state: string }) => `${d.district}, ${d.state}`

/**
 * District type-ahead used on /farmer, /officer and the planner search.
 * >= 640 px: M3 menu rendered in a body portal under the field (never clipped by an overflow ancestor).
 * < 640 px: the field opens an M3 bottom sheet with its own search field (stays above the on-screen keyboard).
 */
export default function DistrictCombobox({
  value, onPick, lang = 'en', big = false, label, placeholder, ariaLabel, fieldBg, rank = 'name', minChars = 1, clearOnPick = false, className = '',
}: {
  value: number | null
  onPick: (lgd: number) => void
  lang?: Lang
  big?: boolean
  label?: string
  placeholder?: string
  ariaLabel?: string
  /** Colour of the surface behind the field (label notch). */
  fieldBg?: string
  /** 'name' = best text match first; 'risk' = highest risk first. */
  rank?: 'name' | 'risk'
  minChars?: number
  /** Empty the field after a pick (search box) instead of showing the picked district. */
  clearOnPick?: boolean
  className?: string
}) {
  const districts = useStore((s) => s.districts)
  const byLgd = useStore((s) => s.byLgd)
  const { key } = useScenario()
  const compact = useMedia('(max-width: 639px)')
  const cur = value != null ? byLgd.get(value) : undefined
  const uid = useId()
  const listId = `${uid}-list`
  const optId = (i: number) => `${uid}-opt-${i}`
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const field = useRef<HTMLLabelElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const menu = useRef<HTMLUListElement>(null)

  useEffect(() => { setText(cur && !clearOnPick ? districtLabel(cur) : '') }, [cur?.lgd, clearOnPick]) // eslint-disable-line react-hooks/exhaustive-deps

  const search = useCallback((q: string, skipLabel?: string): District[] => {
    const s = q.trim().toLowerCase()
    if (s.length < minChars || (skipLabel && q === skipLabel)) return []
    const score = (d: District) => (d.district.toLowerCase().startsWith(s) ? 0 : d.district.toLowerCase().includes(s) ? 1 : d.state.toLowerCase().includes(s) ? 2 : 9)
    return districts
      .map((d) => [score(d), d] as const)
      .filter(([k]) => k < 9)
      .sort((a, b) => (rank === 'risk' ? (b[1].risk[key(b[1])]?.score ?? 0) - (a[1].risk[key(a[1])]?.score ?? 0) : a[0] - b[0]) || a[1].district.localeCompare(b[1].district))
      .slice(0, 12)
      .map(([, d]) => d)
  }, [districts, key, rank, minChars])

  const results = useMemo(() => search(text, cur && !clearOnPick ? districtLabel(cur) : undefined), [search, text, cur, clearOnPick])
  useEffect(() => { setActive(0) }, [text])

  const pickRef = useRef(onPick)
  pickRef.current = onPick
  const choose = useCallback((lgd: number) => {
    setOpen(false)
    if (clearOnPick) setText('')
    pickRef.current(lgd)
  }, [clearOnPick])

  // ---- desktop menu: position under the field, follow scroll / resize
  const [pos, setPos] = useState<{ left: number; top: number; width: number; maxHeight: number; above: boolean } | null>(null)
  const menuOpen = open && !compact && results.length > 0
  const place = useCallback(() => {
    const r = field.current?.getBoundingClientRect()
    if (!r) return
    const below = window.innerHeight - r.bottom - 12, above = r.top - 12
    const flip = below < 240 && above > below
    const maxHeight = Math.max(160, Math.min(window.innerHeight * 0.5, flip ? above : below))
    setPos({ left: r.left + window.scrollX, top: (flip ? r.top : r.bottom) + window.scrollY + (flip ? -4 : 4), width: r.width, maxHeight, above: flip })
  }, [])
  useLayoutEffect(() => {
    if (!menuOpen) return
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => { window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true) }
  }, [menuOpen, place, results.length])

  useEffect(() => {
    if (!menuOpen) return
    const h = (e: MouseEvent) => {
      const t = e.target as Node
      if (field.current?.contains(t) || menu.current?.contains(t)) return
      setOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [menuOpen])

  useEffect(() => { if (menuOpen) document.getElementById(optId(active))?.scrollIntoView({ block: 'nearest' }) }, [active, menuOpen]) // eslint-disable-line react-hooks/exhaustive-deps

  const wasOpen = useRef(false)
  useEffect(() => {
    if (compact && wasOpen.current && !open) input.current?.focus({ preventScroll: true }) // hand focus back to the trigger
    wasOpen.current = open
  }, [open, compact])
  const closeSheet = useCallback(() => setOpen(false), [])

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (compact) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') { e.preventDefault(); setOpen(true) }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!menuOpen) setOpen(true); else setActive((a) => (a + 1) % results.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (menuOpen) setActive((a) => (a - 1 + results.length) % results.length)
    } else if (e.key === 'Enter') {
      if (menuOpen && results[active]) { e.preventDefault(); choose(results[active].lgd) }
    } else if (e.key === 'Escape') {
      if (menuOpen) { e.preventDefault(); e.stopPropagation(); setOpen(false) }
    }
  }

  const fieldStyle = fieldBg ? ({ '--md-field-bg': fieldBg } as CSSProperties) : undefined
  const lbl = label ?? tr(lang, 'home')
  const ph = placeholder ?? tr(lang, 'search')
  const aria = ariaLabel ?? tr(lang, 'pick')

  return (
    <div className={className}>
      <label ref={field} className="md-field" style={fieldStyle}>
        <span className="md-field-label md-body-small">{lbl}</span>
        <input
          ref={input}
          value={text}
          readOnly={compact}
          onChange={(e) => { setText(e.target.value); setOpen(true) }}
          onFocus={(e) => { if (!compact) { e.target.select(); setOpen(true) } }}
          onClick={() => { if (compact) setOpen(true) }}
          onKeyDown={onKey}
          placeholder={ph} aria-label={aria} autoComplete="off" spellCheck={false}
          role="combobox" aria-haspopup="listbox" aria-autocomplete="list"
          aria-expanded={compact ? open : menuOpen} aria-controls={listId}
          aria-activedescendant={menuOpen && results[active] ? optId(active) : undefined}
          className={cx('md-control md-body-large', big && 'min-h-[56px]', compact && 'cursor-pointer')}
        />
      </label>

      {menuOpen && pos && createPortal(
        <ul
          ref={menu} id={listId} role="listbox" aria-label={aria}
          style={{ position: 'absolute', left: pos.left, top: pos.top, width: pos.width, maxHeight: pos.maxHeight, transform: pos.above ? 'translateY(-100%)' : undefined }}
          className="z-[80] overflow-y-auto overscroll-contain rounded-m3-md border border-outline-variant bg-surface-container py-2 shadow-elev-2"
        >
          {results.map((d, i) => <Row key={d.lgd} id={optId(i)} d={d} active={i === active} bandOf={key} onHover={() => setActive(i)} onPick={() => choose(d.lgd)} />)}
        </ul>,
        document.body,
      )}

      {compact && open && (
        <MobileSheet
          title={lbl} placeholder={ph} listId={listId} optId={optId} search={search} bandOf={key} byLabel={aria}
          onClose={closeSheet}
          onPick={choose}
        />
      )}
    </div>
  )
}

type BandOf = ReturnType<typeof useScenario>['key']

function Row({ id, d, active, bandOf, onHover, onPick }: { id: string; d: District; active: boolean; bandOf: BandOf; onHover: () => void; onPick: () => void }) {
  return (
    <li
      id={id} role="option" aria-selected={active}
      onMouseDown={(e) => e.preventDefault()} onMouseMove={onHover} onClick={onPick}
      className={cx('md-state flex min-h-[56px] w-full cursor-pointer items-center justify-between gap-3 px-4 py-2 text-left text-on-surface', active && 'bg-on-surface/[0.08] outline outline-2 -outline-offset-2 outline-secondary')}
    >
      <span className="min-w-0">
        <span className="block truncate md-title-medium">{d.district}</span>
        <span className="block truncate md-body-small text-on-surface-variant">{d.state}</span>
      </span>
      <TrafficLight band={d.risk[bandOf(d)]?.band} variant="dot" />
    </li>
  )
}

/** Bottom sheet with its own search field; the wrapper tracks the visual viewport so the on-screen keyboard never covers the list. */
function MobileSheet({ title, placeholder, listId, optId, search, bandOf, byLabel, onClose, onPick }: {
  title: string; placeholder: string; listId: string; optId: (i: number) => string; search: (q: string) => District[]; bandOf: BandOf; byLabel: string
  onClose: () => void; onPick: (lgd: number) => void
}) {
  const [q, setQ] = useState('')
  const [active, setActive] = useState(0)
  const inp = useRef<HTMLInputElement>(null)
  const results = useMemo(() => search(q), [search, q])
  const [vv, setVv] = useState(() => ({ top: window.visualViewport?.offsetTop ?? 0, height: window.visualViewport?.height ?? window.innerHeight }))
  useEffect(() => { setActive(0) }, [q])
  useEffect(() => {
    const v = window.visualViewport
    if (!v) return
    const h = () => setVv({ top: v.offsetTop, height: v.height })
    v.addEventListener('resize', h); v.addEventListener('scroll', h)
    return () => { v.removeEventListener('resize', h); v.removeEventListener('scroll', h) }
  }, [])
  // Escape closes only this sheet, not a parent sheet that also listens on window.
  useEffect(() => {
    const h = (e: globalThis.KeyboardEvent) => { if (e.key === 'Escape') { e.stopImmediatePropagation(); e.preventDefault(); onClose() } }
    window.addEventListener('keydown', h, true)
    return () => window.removeEventListener('keydown', h, true)
  }, [onClose])
  useEffect(() => { document.getElementById(optId(active))?.scrollIntoView({ block: 'nearest' }) }, [active]) // eslint-disable-line react-hooks/exhaustive-deps

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!results.length) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => (a + 1) % results.length) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => (a - 1 + results.length) % results.length) }
    else if (e.key === 'Enter') { e.preventDefault(); onPick(results[active].lgd) }
  }

  return createPortal(
    <div className="z-[70]" style={{ position: 'fixed', left: 0, top: vv.top, width: '100%', height: vv.height, transform: 'translateZ(0)' }}>
      <Sheet open onClose={onClose} side="bottom" title={title}>
        <div className="px-4 pb-4 pt-3">
          <label className="md-field" style={{ '--md-field-bg': 'rgb(var(--md-rgb-surface-container-low))' } as CSSProperties}>
            <input
              ref={inp} autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
              placeholder={placeholder} aria-label={byLabel} autoComplete="off" spellCheck={false} enterKeyHint="search"
              role="combobox" aria-haspopup="listbox" aria-autocomplete="list" aria-expanded={results.length > 0} aria-controls={listId}
              aria-activedescendant={results[active] ? optId(active) : undefined}
              className="md-control md-body-large min-h-[56px]"
            />
          </label>
          {results.length > 0 ? (
            <ul id={listId} role="listbox" aria-label={byLabel} style={{ maxHeight: Math.max(160, vv.height * 0.88 - 170) }} className="-mx-4 mt-2 overflow-y-auto overscroll-contain py-1">
              {results.map((d, i) => <Row key={d.lgd} id={optId(i)} d={d} active={i === active} bandOf={bandOf} onHover={() => setActive(i)} onPick={() => onPick(d.lgd)} />)}
            </ul>
          ) : (
            <p id={listId} className="px-1 pt-4 md-body-medium text-on-surface-variant" role="status">{placeholder}</p>
          )}
        </div>
      </Sheet>
    </div>,
    document.body,
  )
}

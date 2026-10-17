// Local primitives for the district views, Material 3. Shares class recipes with components/ui (see ui/m3.ts).
import { useId, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { LIGHTS, lightOf } from './copy'
import type { LightKey } from './copy'
import { Button as UiButton, ErrorNote, Icon, type ButtonProps, type IconName } from '../ui'
import { CARD, cx } from '../ui/m3'

export { cx, ErrorNote }

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={cx('animate-pulse rounded-m3-sm bg-surface-container-high', className)} aria-hidden />
}

export function Card({ title, aside, children, className = '', pad = true }: { title?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={cx(CARD, pad && 'p-4', className)}>
      {(title || aside) && (
        <div className="mb-3 flex items-start justify-between gap-2">
          <h3 className="md-title-medium text-on-surface">{title}</h3>
          {aside}
        </div>
      )}
      {children}
    </section>
  )
}

const TONE: Record<LightKey, { dot: string; soft: string; ring: string; text: string }> = {
  low: { dot: 'bg-low-fill', soft: 'bg-low-soft', ring: 'border-low/30', text: 'text-low-ink' },
  watch: { dot: 'bg-watch-fill', soft: 'bg-watch-soft', ring: 'border-watch/30', text: 'text-watch-ink' },
  act: { dot: 'bg-act-fill', soft: 'bg-act-soft', ring: 'border-act/30', text: 'text-act-ink' },
  none: { dot: 'bg-outline-variant', soft: 'bg-surface-container', ring: 'border-outline-variant', text: 'text-muted' },
}
export const toneOf = (k: LightKey) => TONE[k]

/** Three-lamp traffic light inside an M3 assist chip, plus the word. The lit lamp is a filled circle. Colour is never the only signal. */
export function TrafficLight({ band, size = 'md', label, className = '' }: { band: string | null | undefined; size?: 'sm' | 'md' | 'lg'; label?: string; className?: string }) {
  const l = lightOf(band)
  const tone = TONE[l.key]
  const lamp = size === 'lg' ? 'h-3.5 w-3.5' : size === 'sm' ? 'h-2.5 w-2.5' : 'h-3 w-3'
  const text = size === 'lg' ? 'h-10 px-4 md-title-medium' : size === 'sm' ? 'h-6 px-2 md-label-medium' : 'h-8 px-3 md-label-large'
  const order: LightKey[] = ['act', 'watch', 'low']
  const words = label ?? l.label
  return (
    <span role="img" aria-label={`Risk level: ${words}`} className={cx('inline-flex items-center gap-2 rounded-m3-sm border', text, tone.soft, tone.ring, tone.text, className)}>
      <span className="flex items-center gap-1" aria-hidden>
        {order.map((k) => <i key={k} className={cx('block rounded-full', lamp, l.key === k ? `${TONE[k].dot} shadow-[inset_0_0_0_1px_rgb(0_0_0/0.28)]` : 'border border-on-surface/30')} />)}
      </span>
      <span>{words}</span>
    </span>
  )
}

export function Pill({ children, tone = 'neutral', className = '', title }: { children: ReactNode; tone?: 'neutral' | 'info' | 'accent' | 'watch'; className?: string; title?: string }) {
  const c = tone === 'info' ? 'bg-info-soft text-info-ink' : tone === 'accent' ? 'bg-accent-soft text-accent-ink' : tone === 'watch' ? 'bg-watch-soft text-watch-ink' : 'bg-surface-container-high text-muted'
  return <span title={title} className={cx('inline-flex h-6 items-center rounded-m3-sm px-2 md-label-medium', c, className)}>{children}</span>
}

/** Small "estimated" tag with dotted outline; the note explains where the estimate came from. */
export function EstimatedTag({ note }: { note: string | null }) {
  if (!note) return null
  return (
    <span title={note} aria-label={note} tabIndex={0} className="ml-1.5 inline-flex cursor-help items-center rounded-m3-xs border border-dotted border-on-surface/50 px-1.5 align-middle md-label-small text-muted">
      estimated
    </span>
  )
}

export function Stat({ icon, label, value, sub, note, tone }: { icon: IconName; label: string; value: ReactNode; sub?: ReactNode; note?: string | null; tone?: 'bad' | 'good' }) {
  return (
    <div className={cx('flex flex-col p-4', CARD)}>
      <div className="flex items-center gap-1.5 md-label-large text-muted"><span aria-hidden className="flex text-primary"><Icon name={icon} size={20} /></span>{label}<EstimatedTag note={note ?? null} /></div>
      <div className={cx('mt-2 md-title-large', tone === 'bad' ? 'text-act-ink' : 'text-on-surface')}>{value}</div>
      {sub && <div className="mt-1 md-body-small text-muted">{sub}</div>}
    </div>
  )
}

/** Drawer buttons default to filled (primary); same M3 recipes as the shell Button. */
export function Button({ variant = 'primary', ...rest }: ButtonProps) {
  return <UiButton variant={variant} {...rest} />
}

export interface TabDef<T extends string> { id: T; label: string; icon?: IconName }
/** `top`: M3 primary tabs. `bottom`: M3 navigation bar (80 px, active indicator pill). */
export function Tabs<T extends string>({ tabs, value, onChange, idPrefix, variant = 'top', label }: { tabs: TabDef<T>[]; value: T; onChange: (v: T) => void; idPrefix: string; variant?: 'top' | 'bottom'; label: string }) {
  const onKey = (e: KeyboardEvent) => {
    const i = tabs.findIndex((t) => t.id === value)
    let n = -1
    if (e.key === 'ArrowRight') n = (i + 1) % tabs.length
    else if (e.key === 'ArrowLeft') n = (i - 1 + tabs.length) % tabs.length
    else if (e.key === 'Home') n = 0
    else if (e.key === 'End') n = tabs.length - 1
    if (n >= 0) { e.preventDefault(); onChange(tabs[n].id); document.getElementById(`${idPrefix}-tab-${tabs[n].id}`)?.focus() }
  }
  return (
    <div role="tablist" aria-label={label} onKeyDown={onKey} className={variant === 'bottom' ? 'grid bg-surface-container pb-safe' : 'flex gap-1 overflow-x-auto border-b border-outline-variant px-2'} style={variant === 'bottom' ? { gridTemplateColumns: `repeat(${tabs.length}, minmax(0,1fr))` } : undefined}>
      {tabs.map((t) => {
        const on = t.id === value
        return (
          <button
            key={t.id} role="tab" id={`${idPrefix}-tab-${t.id}`} aria-selected={on} aria-controls={`${idPrefix}-panel-${t.id}`} tabIndex={on ? 0 : -1} onClick={() => onChange(t.id)}
            className={cx(
              'md-state md-focus-inset relative whitespace-nowrap transition-colors',
              variant === 'bottom' ? 'flex h-20 flex-col items-center justify-center gap-1 px-1 pb-4 pt-3 md-label-medium' : 'min-h-12 px-4 md-label-large',
              variant === 'bottom' ? (on ? 'text-on-surface' : 'text-on-surface-variant') : on ? 'text-primary' : 'text-on-surface-variant',
            )}
          >
            {variant === 'bottom' && t.icon && (
              <span className={cx('flex h-8 w-16 items-center justify-center rounded-full transition-colors', on && 'bg-secondary-container text-on-secondary-container')}><Icon name={t.icon} fill={on} /></span>
            )}
            {t.label}
            {variant === 'top' && on && <i className="absolute inset-x-3 bottom-0 h-[3px] rounded-t-full bg-primary" aria-hidden />}
          </button>
        )
      })}
    </div>
  )
}
export function TabPanel({ id, idPrefix, active, children, className = '' }: { id: string; idPrefix: string; active: boolean; children: ReactNode; className?: string }) {
  if (!active) return null
  return <div role="tabpanel" id={`${idPrefix}-panel-${id}`} aria-labelledby={`${idPrefix}-tab-${id}`} tabIndex={0} className={className}>{children}</div>
}

export function Accordion({ title, children, defaultOpen = false }: { title: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  const id = useId()
  return (
    <div className={CARD}>
      <button aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)} className="md-state flex min-h-14 w-full items-center justify-between gap-2 rounded-m3-md px-4 text-left md-title-medium text-on-surface">
        {title}
        <Icon name="expand_more" className={cx('text-on-surface-variant transition-transform', open && 'rotate-180')} />
      </button>
      {open && <div id={id} className="space-y-4 border-t border-outline-variant p-4">{children}</div>}
    </div>
  )
}

/** Icon in a secondary-container circle, followed by a sentence. */
export function IconSentence({ icon, children, weight }: { icon: IconName; children: ReactNode; weight?: number }) {
  return (
    <li className="flex items-start gap-3">
      <span aria-hidden className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-secondary-container text-on-secondary-container"><Icon name={icon} size={22} /></span>
      <div className="min-w-0 flex-1 pt-1.5 md-body text-on-surface">
        {children}
        {weight != null && <div className="mt-2 h-1 w-24 rounded-full bg-surface-container-highest" aria-hidden><div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(8, weight * 100)}%` }} /></div>}
      </div>
    </li>
  )
}

export { LIGHTS }

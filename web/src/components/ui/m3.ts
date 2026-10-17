// Material 3 class recipes shared by the shell primitives (components/ui) and the drawer primitives (components/drawer/ui).
// Colours are Tailwind aliases of the M3 roles in src/m3.css; shapes use the M3 scale (rounded-m3-*).
export const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(' ')

export type BtnVariant = 'primary' | 'secondary' | 'outlined' | 'ghost' | 'danger'
/** primary = filled, secondary = tonal, outlined, ghost = text, danger = filled error. */
export const BTN_V: Record<BtnVariant, string> = {
  primary: 'bg-primary text-on-primary disabled:bg-on-surface/10 disabled:text-on-surface/40',
  secondary: 'bg-secondary-container text-on-secondary-container disabled:bg-on-surface/10 disabled:text-on-surface/40',
  outlined: 'border border-outline bg-transparent text-primary disabled:border-on-surface/15 disabled:text-on-surface/40',
  ghost: 'bg-transparent text-primary disabled:text-on-surface/40',
  danger: 'bg-error text-on-error disabled:bg-on-surface/10 disabled:text-on-surface/40',
}
// sm = 40 px visual (+ hit area to 48), md = 48, lg = 56 (farmer / primary calls to action)
export const BTN_S = { sm: 'h-10 px-4 md-label-large md-hit', md: 'min-h-[48px] px-6 md-label-large', lg: 'min-h-[56px] px-8 md-title-medium' }
export const BTN_BASE = 'md-state inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full font-medium transition-shadow disabled:cursor-not-allowed'

/** Filled / outlined card surface: surface-container-low with an outline-variant border, no heavy shadow. */
export const CARD = 'rounded-m3-md border border-outline-variant bg-surface-container-low'

export const CHIP_BASE = 'md-state md-hit relative inline-flex shrink-0 items-center justify-center gap-2 rounded-m3-sm border md-label-large transition-colors'
export const CHIP_ON = 'border-transparent bg-secondary-container text-on-secondary-container'
export const CHIP_OFF = 'border-outline bg-transparent text-on-surface-variant'

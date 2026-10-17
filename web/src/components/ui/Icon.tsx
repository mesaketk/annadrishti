import type { IconName } from '../../lib/icons'

export type { IconName }
/** Material Symbols Rounded glyph. `fill` toggles the FILL axis (selected / active states). Decorative: hidden from AT. */
export function Icon({ name, fill = false, size = 24, className = '', weight = 400 }: { name: IconName; fill?: boolean; size?: number; className?: string; weight?: number }) {
  return (
    <span
      aria-hidden
      className={`material-symbols-rounded ${className}`}
      style={{ fontSize: size, fontVariationSettings: `'FILL' ${fill ? 1 : 0}, 'wght' ${weight}, 'GRAD' 0, 'opsz' ${Math.min(48, Math.max(20, size))}` }}
    >
      {name}
    </span>
  )
}

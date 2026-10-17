// Hex mirrors of the M3 tokens (src/m3.css via lib/m3.ts), for Recharts props that cannot take classes.
// Charts: primary for lines, error-container for El Nino shading, outline-variant for the grid.
import { M3 } from '../../lib/m3'

export const C = {
  ink: M3.onSurface, muted: M3.onSurfaceVariant, line: M3.outlineVariant, bg: M3.surface, surface: M3.surfaceContainerLow,
  low: M3.lowFill, watch: M3.watchFill, act: M3.error, info: M3.tertiary, accent: M3.primary, nodata: M3.outlineVariant,
  elnino: M3.errorContainer, actStrong: M3.actFill,
} as const
export const AXIS = { stroke: C.line, tick: { fill: C.muted, fontSize: 12 }, tickLine: false } as const

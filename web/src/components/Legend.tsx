import { useState } from 'react'
import type { LayerId, Scale } from '../lib/scales'
import { BAND_COLOR, HIT_COLOR } from '../lib/scales'
import { Icon } from './ui'
import type { HistoryLayerId } from '../lib/history'
import { useStore } from '../lib/store'

const Swatch = ({ color, hatch, dotted }: { color?: string; hatch?: boolean; dotted?: boolean }) => (
  <i
    className={`inline-block h-4 w-4 shrink-0 rounded-m3-xs ${hatch ? 'hatch border border-outline-variant' : ''} ${dotted ? 'border-2 border-dotted border-on-surface bg-surface' : ''} ${color ? 'shadow-[inset_0_0_0_1px_rgb(0_0_0/0.18)]' : ''}`}
    style={color ? { background: color } : undefined}
  />
)
const Item = ({ children, ...p }: { children: string; color?: string; hatch?: boolean; dotted?: boolean }) => (
  <li className="flex items-center gap-2"><Swatch {...p} />{children}</li>
)

/** Plain-word legend for the active map layer (now or history). */
export default function Legend({ scale, layer, compact, window: win }: { scale: Scale; layer: LayerId | HistoryLayerId; compact?: boolean; window?: string }) {
  const mode = useStore((s) => s.mode)
  const [open, setOpen] = useState(!compact)
  const bands = layer === 'risk' || layer === 'h_tool'
  const hit = layer === 'h_hit'
  const lo = scale.stops[0][0], hi = scale.stops[scale.stops.length - 1][0]
  const grad = scale.stops.map(([v, c]) => `${c} ${(((v - lo) / (hi - lo)) * 100).toFixed(1)}%`).join(', ')
  const title = layer === 'h_rain' ? 'What happened: monsoon rain' : layer === 'h_yield' ? 'What happened: harvest' : layer === 'h_tool' ? 'What the tool would have said' : hit ? 'Did the warning match what happened?' : layer === 'risk' ? 'Risk this season' : scale.label
  return (
    <div className="absolute bottom-6 left-3 z-10 max-w-[calc(100%-1.5rem)] rounded-m3-md bg-surface-container-low p-3 shadow-elev-1 md-body-medium text-on-surface" style={{ width: bands || hit ? 'auto' : 280 }}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="md-state md-focus-inset -m-1 flex w-[calc(100%+0.5rem)] items-center justify-between gap-3 rounded-m3-sm p-1 text-left md-title-small">
        {title}<Icon name="expand_more" size={20} className={`text-on-surface-variant transition-transform ${open ? '' : '-rotate-90'}`} />
      </button>
      {open && (
        <div className="mt-2">
          {bands && (
            <ul className="space-y-1.5">
              <Item color={BAND_COLOR.high}>Act now</Item>
              <Item color={BAND_COLOR.medium}>Watch</Item>
              <Item color={BAND_COLOR.low}>Low risk</Item>
              {layer === 'risk' && mode === 'now' && <Item dotted>Estimated from nearby data (dotted)</Item>}
              <Item hatch>No estimate</Item>
            </ul>
          )}
          {hit && (
            <ul className="space-y-1.5">
              <Item color={HIT_COLOR.hit}>Warned and harvest fell</Item>
              <Item color={HIT_COLOR.miss}>Harvest fell, not warned</Item>
              <Item color={HIT_COLOR.noloss}>No harvest loss</Item>
              <Item hatch>No estimate</Item>
            </ul>
          )}
          {!bands && !hit && (
            <>
              <div className="h-3 rounded-m3-xs" style={{ background: `linear-gradient(90deg, ${grad})` }} />
              <div className="mt-1.5 flex justify-between gap-2 md-body-small text-muted"><span>← {scale.lowLabel}</span><span>{scale.highLabel} →</span></div>
              {layer === 'season_rain' && <div className="mt-1 md-body-small text-muted">Expected vs normal{win ? ` for ${win}` : ' for the coming season'}</div>}
              <div className="mt-2 flex items-center gap-2 md-body-small text-muted"><Swatch hatch />No estimate</div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

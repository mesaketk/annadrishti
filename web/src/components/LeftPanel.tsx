import { useEffect, useMemo, useState } from 'react'
import { useStore } from '../lib/store'
import { useScenario } from '../lib/useScenario'
import { LAYERS, LAYER_GROUPS, type LayerId } from '../lib/scales'
import { HISTORY_LAYERS } from '../lib/history'
import { gwStress, marketSpike } from '../lib/extra'
import { outlookOf } from '../lib/scenario'
import { Icon, TrafficLight, Segmented, SelectField } from './ui'

/** Map layers (grouped, plain names), district search and state filter. */
export default function LeftPanel({ className = '', onPick, hideSearch }: { className?: string; onPick?: () => void; hideSearch?: boolean }) {
  const { districts, layer, setLayer, nfhs, setNfhs, stateFilter, setStateFilter, select, mode, historyLayer, setHistoryLayer } = useStore()
  const { key: keyOf, season, phase } = useScenario()
  const [q, setQ] = useState('')
  const hist = mode === 'history'
  const hasLive = useMemo(() => districts.some((d) => d.climate?.live), [districts])
  const hasData = useMemo(() => ({
    markets: districts.some((d) => marketSpike(d) != null),
    groundwater: districts.some((d) => gwStress(d) != null),
    season_outlook: districts.some((d) => outlookOf(d, season, phase)?.rain_anom_pct != null),
  }), [districts, season, phase])
  const layers = LAYERS.filter((l) => !l.needs || hasData[l.needs])
  useEffect(() => { if (!layers.some((l) => l.id === layer)) setLayer('risk') }, [layers.length, hasData.season_outlook]) // eslint-disable-line react-hooks/exhaustive-deps
  const states = useMemo(() => [...new Set(districts.map((d) => d.state))].sort(), [districts])
  const results = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (s.length < 2) return []
    return districts
      .filter((d) => d.district.toLowerCase().includes(s) || d.state.toLowerCase().includes(s))
      .sort((a, b) => (b.risk[keyOf(b)]?.score ?? 0) - (a.risk[keyOf(a)]?.score ?? 0))
      .slice(0, 8)
  }, [q, districts, keyOf])

  // M3 navigation-drawer item: 48 px pill, secondary-container active indicator
  const radio = (on: boolean, disabled = false) =>
    `md-state md-focus-inset flex min-h-[48px] w-full items-center gap-3 rounded-full px-4 py-1.5 text-left md-label-large transition-colors ${on ? 'bg-secondary-container text-on-secondary-container' : 'text-on-surface-variant'} ${disabled ? 'cursor-not-allowed opacity-40' : ''}`

  return (
    <aside className={`flex flex-col gap-5 overflow-y-auto border-r border-outline-variant bg-surface-container-low p-3 ${className}`} aria-label="Map controls">
      <div>
        {!hideSearch && <>
        <label className="md-field mt-2" style={{ '--md-field-bg': 'rgb(var(--md-rgb-surface-container-low))' } as React.CSSProperties}>
          <span className="md-field-label md-body-small">Find a district</span>
          <input
            id="q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="District or state…" autoComplete="off"
            className="md-control md-body-large"
          />
          {results.length > 0 && (
            <ul className="absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-m3-xs bg-surface-container py-2 shadow-elev-2">
              {results.map((d) => (
                <li key={d.lgd}>
                  <button className="md-state flex min-h-[56px] w-full items-center justify-between gap-2 px-4 py-1.5 text-left md-body-medium"
                    onClick={() => { select(d.lgd, true); useStore.getState().setView('map'); setQ(''); onPick?.() }}>
                    <span><b className="font-medium">{d.district}</b><br /><span className="md-body-small text-muted">{d.state}</span></span>
                    <TrafficLight band={d.risk[keyOf(d)]?.band} variant="dot" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </label>
        </>}
        <SelectField label="Show one state" id="st" value={stateFilter} onChange={setStateFilter} className={hideSearch ? 'mt-2' : 'mt-5'} fieldBg="surface-container-low">
          <option value="">All of India</option>
          {states.map((s) => <option key={s} value={s}>{s}</option>)}
        </SelectField>
      </div>

      {hist ? (
        <div>
          <div className="mb-2 px-4 md-title-small text-on-surface-variant">Look back</div>
          <div role="radiogroup" className="flex flex-col gap-0.5">
            {HISTORY_LAYERS.map((l) => (
              <button key={l.id} role="radio" aria-checked={historyLayer === l.id} onClick={() => setHistoryLayer(l.id)} title={l.hint} className={radio(historyLayer === l.id)}>
                <Icon name={l.icon} fill={historyLayer === l.id} size={22} />{l.name}
              </button>
            ))}
          </div>
          <p className="mt-2 px-4 md-body-small text-muted">{HISTORY_LAYERS.find((l) => l.id === historyLayer)?.hint}.</p>
        </div>
      ) : (
        <div>
          <div className="mb-2 px-4 md-title-small text-on-surface-variant">What to show on the map</div>
          {LAYER_GROUPS.map((g) => {
            const items = layers.filter((l) => l.group === g)
            if (!items.length) return null
            return (
              <div key={g} className="mb-2">
                <div className="mb-0.5 px-4 pt-2 md-label-medium text-on-surface-variant">{g}</div>
                <div role="radiogroup" className="flex flex-col gap-0.5">
                  {items.map((l) => {
                    const disabled = !!l.needsLive && !hasLive
                    const on = layer === l.id
                    return (
                      <div key={l.id}>
                        <button role="radio" aria-checked={on} disabled={disabled} onClick={() => setLayer(l.id as LayerId)} title={disabled ? 'Not available in this data set' : l.hint} className={radio(on, disabled)}>
                          <Icon name={l.icon} fill={on} size={22} />{l.name}
                        </button>
                        {(l.id === 'stunting' || l.id === 'anaemia') && on && (
                          <div className="my-2 ml-12">
                            <Segmented size="sm" value={nfhs} onChange={setNfhs} options={[{ id: 'nfhs5', label: 'Survey 2019–21', title: 'NFHS-5' }, { id: 'nfhs6', label: 'Survey 2023–24', title: 'NFHS-6' }]} />
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
          <p className="mt-2 px-4 md-body-small text-muted">{LAYERS.find((l) => l.id === layer)?.hint}. Orange always means worse.</p>
        </div>
      )}
    </aside>
  )
}

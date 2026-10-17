import { useEffect, useMemo, useRef, useState } from 'react'
import maplibregl, { type StyleSpecification } from 'maplibre-gl'
import type { Geometry } from 'geojson'
import { useStore } from '../lib/store'
import { useScenario } from '../lib/useScenario'
import { BAND_COLOR, HIT_COLOR, NULL_COLOR, colorFor, getScale, layerValue, thresholdsOf } from '../lib/scales'
import { M3 } from '../lib/m3'
import { geoPromise, statesPromise, type DistrictFC as FC } from '../lib/geo'
import { hitKind, useHistoryYear, type HistDistrict, type HistoryLayerId } from '../lib/history'
import { bandWord, districtSentence, isImputed } from '../lib/plain'
import type { District } from '../types'
import { Spinner, TrafficLight } from './ui'
import Legend from './Legend'

const STYLE_URL = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json'
const BLANK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': M3.surface } }],
}

/** Diagonal hatch tile used on top of "no estimate" districts. */
function hatchImage(): ImageData {
  const n = 8
  const c = document.createElement('canvas')
  c.width = c.height = n
  const x = c.getContext('2d')!
  x.strokeStyle = `${M3.onSurfaceVariant}8c`
  x.lineWidth = 1.2
  x.beginPath()
  for (const o of [-n, 0, n]) { x.moveTo(o, n); x.lineTo(o + n, 0) }
  x.stroke()
  return x.getImageData(0, 0, n, n)
}

interface Painted { c: string; noData: boolean; imputed: boolean }
const NODATA: Painted = { c: '', noData: true, imputed: false }
const INDIA_BOUNDS: [[number, number], [number, number]] = [[68.1, 6.4], [97.5, 35.8]]

function bboxOf(geom: Geometry): [number, number, number, number] {
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90
  const walk = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === 'number') {
      const [x, y] = c as number[]
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y
    } else if (Array.isArray(c)) c.forEach(walk)
  }
  walk((geom as { coordinates?: unknown }).coordinates)
  return [x0, y0, x1, y1]
}

async function pickStyle(): Promise<string | StyleSpecification> {
  try {
    const ctl = new AbortController()
    const t = setTimeout(() => ctl.abort(), 4000)
    const r = await fetch(STYLE_URL, { signal: ctl.signal })
    clearTimeout(t)
    if (r.ok) return STYLE_URL
  } catch { /* offline: fall through */ }
  return BLANK_STYLE
}

export default function MapView({ compact = false, onSelect }: { compact?: boolean; onSelect?: (lgd: number) => void }) {
  const box = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const geoRef = useRef<FC | null>(null)
  const hoverRef = useRef<number | null>(null)
  const selRef = useRef<number | null>(null)
  const [ready, setReady] = useState(false)
  const [painted, setPainted] = useState(false)
  const [hover, setHover] = useState<{ lgd: number; x: number; y: number } | null>(null)
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect

  const { districts, byLgd, layer: nowLayer, nfhs, stateFilter, selected, flyNonce, kpis, mode, year, historyLayer } = useStore()
  const { season, phase, key: keyOf } = useScenario()
  const hist = mode === 'history'
  const layer = hist ? historyLayer : nowLayer
  const H = useHistoryYear(year, hist)
  const hy = hist ? H.data : null // keep previous year on screen while the next one loads
  const thr = thresholdsOf(kpis)
  const scale = useMemo(() => {
    if (layer === 'h_rain') return getScale('rain_anom')
    if (layer === 'h_yield') return getScale('yield_shock')
    if (layer === 'h_tool' || layer === 'h_hit') return getScale('risk', nfhs, thr)
    return getScale(layer, nfhs, thr)
  }, [layer, nfhs, thr.low_below, thr.high_from]) // eslint-disable-line react-hooks/exhaustive-deps

  const paintOf = (d: District | undefined, lgd: number): Painted => {
    if (hist) {
      const h: HistDistrict | undefined = hy?.districts?.[String(lgd)]
      if (!h) return NODATA
      const hl = layer as HistoryLayerId
      if (hl === 'h_rain') return h.rain_anom_pct == null ? NODATA : { c: colorFor(scale, h.rain_anom_pct), noData: false, imputed: false }
      if (hl === 'h_yield') return h.yield_dev_pct == null ? NODATA : { c: colorFor(scale, h.yield_dev_pct), noData: false, imputed: false }
      if (hl === 'h_tool') return !h.tool_band || h.tool_band === 'no_data' ? NODATA : { c: BAND_COLOR[h.tool_band], noData: false, imputed: false }
      const k = hitKind(h)
      return k === 'nodata' ? NODATA : { c: HIT_COLOR[k], noData: false, imputed: false }
    }
    if (!d) return NODATA
    const k = keyOf(d)
    if (layer === 'risk') {
      const b = d.risk[k]?.band
      return !b || b === 'no_data' ? NODATA : { c: BAND_COLOR[b], noData: false, imputed: isImputed(d, k) }
    }
    const v = layerValue(d, layer as Parameters<typeof layerValue>[1], k, nfhs)
    return v == null ? NODATA : { c: colorFor(scale, v), noData: false, imputed: false }
  }

  // ---- init map once
  useEffect(() => {
    let disposed = false
    let map: maplibregl.Map | null = null
    ;(async () => {
      const [style, geo] = await Promise.all([pickStyle(), geoPromise])
      if (disposed || !box.current) return
      geoRef.current = geo
      map = new maplibregl.Map({
        container: box.current, style, bounds: INDIA_BOUNDS, fitBoundsOptions: { padding: 12 },
        attributionControl: { compact: true }, minZoom: 3, maxZoom: 10, dragRotate: false, pitchWithRotate: false, cooperativeGestures: false,
      })
      mapRef.current = map
      map.touchZoomRotate.disableRotation()
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
      map.on('load', async () => {
        const m = map!
        const states = await statesPromise
        const firstSymbol = m.getStyle().layers?.find((l) => l.type === 'symbol')?.id
        if (!m.hasImage('hatch')) m.addImage('hatch', hatchImage())
        m.addSource('districts', { type: 'geojson', data: geo, promoteId: 'lgd' })
        m.addSource('states', { type: 'geojson', data: states })
        m.addLayer({
          id: 'd-fill', type: 'fill', source: 'districts',
          paint: {
            'fill-color': ['case', ['==', ['to-string', ['feature-state', 'c']], ''], NULL_COLOR, ['to-color', ['feature-state', 'c']]],
            'fill-opacity': ['case', ['boolean', ['feature-state', 'dim'], false], 0.12, 0.82],
          },
        }, firstSymbol)
        // "no estimate": diagonal hatch over the grey fill (filter is refreshed whenever the paint changes)
        m.addLayer({
          id: 'd-nodata', type: 'fill', source: 'districts', filter: ['in', ['get', 'lgd'], ['literal', []]],
          paint: { 'fill-pattern': 'hatch', 'fill-opacity': 0.9 },
        }, firstSymbol)
        m.addLayer({ id: 'd-line', type: 'line', source: 'districts', paint: { 'line-color': M3.surfaceBright, 'line-width': 0.45, 'line-opacity': 0.85 } }, firstSymbol)
        // estimated (imputed) values: dotted outline in the same place the value is shown
        m.addLayer({
          id: 'd-imputed', type: 'line', source: 'districts', filter: ['in', ['get', 'lgd'], ['literal', []]],
          paint: { 'line-color': M3.onSurface, 'line-width': 1.6, 'line-dasharray': [0.5, 2], 'line-opacity': 0.9 }, layout: { 'line-cap': 'round' },
        }, firstSymbol)
        m.addLayer({ id: 's-line', type: 'line', source: 'states', paint: { 'line-color': M3.onSurface, 'line-width': 0.8, 'line-opacity': 0.4 } }, firstSymbol)
        m.addLayer({
          id: 'd-hl', type: 'line', source: 'districts',
          paint: {
            'line-color': ['case', ['boolean', ['feature-state', 'selected'], false], M3.onSurface, M3.primary],
            'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2.4, ['boolean', ['feature-state', 'hover'], false], 1.8, 0],
          },
        })

        m.on('mousemove', 'd-fill', (e) => {
          const f = e.features?.[0]
          const lgd = f ? Number(f.id ?? f.properties?.lgd) : null
          m.getCanvas().style.cursor = 'pointer'
          if (lgd !== hoverRef.current) {
            if (hoverRef.current != null) m.setFeatureState({ source: 'districts', id: hoverRef.current }, { hover: false })
            if (lgd != null) m.setFeatureState({ source: 'districts', id: lgd }, { hover: true })
            hoverRef.current = lgd
          }
          if (lgd != null) setHover({ lgd, x: e.point.x, y: e.point.y })
        })
        m.on('mouseleave', 'd-fill', () => {
          m.getCanvas().style.cursor = ''
          if (hoverRef.current != null) m.setFeatureState({ source: 'districts', id: hoverRef.current }, { hover: false })
          hoverRef.current = null
          setHover(null)
        })
        m.on('click', 'd-fill', (e) => {
          const f = e.features?.[0]
          if (!f) return
          const lgd = Number(f.id ?? f.properties?.lgd)
          if (onSelectRef.current) onSelectRef.current(lgd)
          else useStore.getState().select(lgd)
        })
        setReady(true)
      })
    })()
    return () => {
      disposed = true
      map?.remove()
      mapRef.current = null
      setReady(false)
    }
  }, [])

  // ---- keep the canvas in step with its container (sheets, column changes)
  useEffect(() => {
    const el = box.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => mapRef.current?.resize())
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // ---- paint choropleth
  useEffect(() => {
    const m = mapRef.current
    const geo = geoRef.current
    if (!ready || !m || !geo) return
    const none: number[] = [], dotted: number[] = []
    for (const f of geo.features) {
      const lgd = f.properties.lgd
      const p = paintOf(byLgd.get(lgd), lgd)
      if (p.noData) none.push(lgd)
      if (p.imputed) dotted.push(lgd)
      m.setFeatureState({ source: 'districts', id: lgd }, { c: p.c, dim: stateFilter !== '' && f.properties.state !== stateFilter })
    }
    m.setFilter('d-nodata', ['in', ['get', 'lgd'], ['literal', none]])
    m.setFilter('d-imputed', ['in', ['get', 'lgd'], ['literal', dotted]])
    // reveal after the first frame with colours has actually been drawn
    const raf = requestAnimationFrame(() => requestAnimationFrame(() => setPainted(true)))
    return () => cancelAnimationFrame(raf)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, districts, byLgd, layer, season, phase, nfhs, scale, stateFilter, hist, hy])

  // ---- selection highlight
  useEffect(() => {
    setHover(null)
    const m = mapRef.current
    if (!ready || !m) return
    if (selRef.current != null) m.setFeatureState({ source: 'districts', id: selRef.current }, { selected: false })
    if (selected != null) m.setFeatureState({ source: 'districts', id: selected }, { selected: true })
    selRef.current = selected
  }, [ready, selected])

  // ---- camera: fly to selected district when requested (search / chat / planner)
  useEffect(() => {
    const m = mapRef.current
    const geo = geoRef.current
    if (!ready || !m || !geo || flyNonce === 0 || selected == null) return
    const f = geo.features.find((x) => x.properties.lgd === selected)
    if (!f) return
    const [x0, y0, x1, y1] = bboxOf(f.geometry)
    m.fitBounds([[x0, y0], [x1, y1]], { padding: compact ? 30 : 90, maxZoom: 7.5, duration: 900 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flyNonce, ready])

  // ---- camera: state filter
  useEffect(() => {
    const m = mapRef.current
    const geo = geoRef.current
    if (!ready || !m || !geo) return
    if (!stateFilter) { m.fitBounds(INDIA_BOUNDS, { padding: 12, duration: 700 }); return }
    let x0 = 180, y0 = 90, x1 = -180, y1 = -90
    for (const f of geo.features) {
      if (f.properties.state !== stateFilter) continue
      const b = bboxOf(f.geometry)
      x0 = Math.min(x0, b[0]); y0 = Math.min(y0, b[1]); x1 = Math.max(x1, b[2]); y1 = Math.max(y1, b[3])
    }
    if (x1 > x0) m.fitBounds([[x0, y0], [x1, y1]], { padding: 50, duration: 800, maxZoom: 8 })
  }, [stateFilter, ready])

  const hd = hover ? byLgd.get(hover.lgd) : null
  const hk = hd ? keyOf(hd) : ''
  const hh = hover && hy ? hy.districts?.[String(hover.lgd)] : undefined
  const box2 = box.current?.getBoundingClientRect()
  const nf = (v: number | null | undefined, unit = ' %') => (v == null ? 'no data' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(0)}${unit}`)
  const tipSentence = !hd ? '' : hist
    ? (() => {
        const k = hitKind(hh)
        const outcome = k === 'hit' ? 'The tool would have warned, and the harvest fell.' : k === 'miss' ? 'Harvest fell, but the tool would not have warned.' : k === 'noloss' ? 'Harvest held up (less than 5 % below trend).' : 'No harvest data for this year.'
        return `${year}: rain ${nf(hh?.rain_anom_pct)} vs normal, harvest ${nf(hh?.yield_dev_pct)} vs trend. ${outcome}`
      })()
    : layer === 'risk' ? districtSentence(hd, hk, kpis) : `${scale.label}: ${(() => { const v = layerValue(hd, layer as Parameters<typeof layerValue>[1], hk, nfhs); return v == null ? 'no estimate' : scale.format(v) })()}`
  const tipBand = hist ? (hh?.tool_band ?? null) : hd?.risk[hk]?.band

  return (
    <div className="relative h-full w-full overflow-hidden bg-surface-container">
      <div ref={box} className="absolute inset-0" />
      <Legend scale={scale} layer={layer} compact={compact} />
      {hist && H.error && (
        <div className="absolute left-1/2 top-3 z-10 -translate-x-1/2 rounded-m3-xs bg-inverse-surface px-4 py-3 md-body-medium text-inverse-on-surface shadow-elev-2" role="status">History not available yet</div>
      )}
      {!(ready && painted) && (
        <div className="absolute inset-0 z-20 grid place-items-center bg-surface" aria-busy="true">
          <Spinner label="Loading map…" />
        </div>
      )}
      {hover && hd && (
        <div
          role="tooltip" className="pointer-events-none absolute z-10 w-64 rounded-m3-sm bg-inverse-surface p-3 md-body-small text-inverse-on-surface shadow-elev-2"
          style={{
            left: Math.max(4, Math.min(hover.x + 14, (box2?.width ?? 800) - 268)),
            top: Math.max(4, Math.min(hover.y + 14, (box2?.height ?? 600) - 150)),
          }}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0"><div className="truncate md-label-large">{hd.district}</div><div className="truncate md-body-small opacity-80">{hd.state}</div></div>
            <TrafficLight band={tipBand} />
          </div>
          <p className="mt-2">{tipSentence}</p>
          {!hist && layer === 'risk' && isImputed(hd, hk) && <p className="mt-1 opacity-80">Dotted outline: partly estimated from nearby data.</p>}
          {tipBand == null && <p className="mt-1 opacity-80">{bandWord(null)}</p>}
        </div>
      )}
    </div>
  )
}

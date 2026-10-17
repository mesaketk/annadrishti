# AnnaDrishti web

React 18 + Vite + TypeScript, MapLibre GL (choropleth), Recharts, Tailwind, zustand, react-markdown.

```bash
npm i && npm run dev        # http://localhost:5173  (proxies /api -> http://localhost:8080)
npm run build               # type-check + production build into web/dist
```

(If `npm i` misbehaves in a restricted sandbox, `pnpm i --config.node-linker=hoisted` produces the same node_modules.)

## Data

* The app calls `/api/districts`, `/api/kpis`, `/api/timeseries/{lgd}`, `/api/actions`, `POST /api/advisory/{lgd}`,
  `POST /api/advisory/{lgd}/audio`, `POST /api/state_brief`, `POST /api/chat` (see `docs/SCHEMA.md`).
* If `/api/districts` or `/api/kpis` fails, it falls back automatically to `public/mock/*` and shows a **demo data** badge.
  In mock mode the Gemini endpoints return clearly labelled canned text so the UI can be exercised offline.
* Regenerate mock data: `python3 web/scripts/make_mock.py` (needs `public/districts.geojson`, numpy, shapely).
* Regenerate boundaries: `python3 pipeline/00_boundaries.py` (writes `public/districts.geojson` + `states.geojson`).

## Layout

```
src/types.ts            TS interfaces mirroring docs/SCHEMA.md
src/lib/api.ts          fetch helpers, mock fallback, planner row normalisation
src/lib/scales.ts       layers, colour scales (red = bad), scenario labels
src/lib/store.ts        zustand store (scenario, layer, selection, view, data)
src/components/         TopBar, KpiStrip, LeftPanel, MapView, Legend, DistrictDrawer,
                        HindcastCard, AdvisoryPanel (text + audio), Planner, ChatPanel
```

The basemap is the free CARTO Dark Matter style; if it cannot be fetched the map falls back to a plain dark background.

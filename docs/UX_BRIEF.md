# UX brief v2 — "for farmers and officers, not analysts"

## Users and jobs
| Role | Entry | Job in 30 seconds |
|---|---|---|
| **Farmer** (phone, low literacy, local language) | pick my district (or GPS) → one card | "Is my season risky? What should I sow? Where do I get seed/insurance?" + listen |
| **District officer** (Collector / dept) | pick district + department | "Is my district flagged, who is at risk, my 5 actions, by when" |
| **State / national planner** | map + planner | "Which districts first, how much to pre‑position, which dept does what" |

Role picker on first load (remembered in localStorage), switchable in the header. Default route per role.

## Information architecture (progressive disclosure)
- **Level 0 — the answer**: traffic light (🟢 Low / 🟡 Watch / 🔴 Act) + one plain sentence ("Nandurbar: high risk this Kharif if El Niño persists — mainly rainfed crops and child nutrition"). No numbers beyond 1–2.
- **Level 1 — tabs**: `Overview · Why · Trends · Actions · Advisory` (officer) / `Advice · Why · Trends` (farmer).
  - Overview: traffic light, season + outlook sentence, 4 plain "facts" tiles (people, children, expected harvest change, PDS cover).
  - Why: top 3 drivers as sentences with icons (💧 rain, 🌾 crops, 👶 nutrition, 💰 prices, 🚰 groundwater); "see full breakdown" → accordion with all drivers + component gauges + model agreement.
  - Trends: **time‑series charts visible by default**: foodgrain yield 2000–2024 with El Niño years shaded, monsoon rainfall anomaly bars, NFHS‑4→5→6 nutrition lines, Poshan monthly underweight, PDS monthly offtake, price series. Each chart has a one‑line caption in plain words.
  - Actions: season‑specific pre‑positioning card (quantities + lead dates + responsible dept) and department briefing (Gemini) behind a clear button.
  - Advisory (farmer): profile form (big touch targets), advisory text, ▶ Listen, share (WhatsApp link / copy), "where to get help" (KVK, agriculture office, PMFBY portal, PDS shop).
- **Level 2 — Methods** page (existing modal content) for the technical reader; "Data & methods" link in footer.

## Visual system (light)
- Tokens (Tailwind): `bg #F7F8F5`, `surface #FFFFFF`, `ink #1F2A1F`, `muted #5C6B5C`, `line #E3E8E0`; semantic: `low #2E8B57`, `watch #E0A100`, `act #C8372D`, `info #2F6DB5`, `accent #3E7C3A` (leaf green), `no‑data #CBD2C9` with diagonal hatch, `imputed` = same colour as value + dotted outline.
- Type: Inter (UI) + Noto Sans Devanagari/Telugu/Tamil/Bengali/Kannada/Gujarati/Odia via Google Fonts for local scripts; base 16 px, farmer view 18 px; min touch target 44 px.
- Map: light basemap (CARTO positron), choropleth in the 3 semantic colours only for the "risk" layer (no 0–100 gradient on the default view); gradient layers keep sequential/diverging scales with plain legends ("drier than normal → wetter than normal").
- Charts: Recharts, muted grid, one accent per chart, El Niño years shaded `#FDECEA`, annotations in words.
- Plain‑language rules: no acronyms without expansion on first use (NFHS → "national health survey (NFHS)"), no "ρ", no "tertile", no "rank‑normalised" outside Methods. Numbers rounded (1 decimal max), units always spelled ("lakh tonnes", "children under 5").
- Mobile first for the farmer route (375 px): single column, sticky district name + traffic light, bottom tab bar.

## Missing data policy (shown to users)
- Every imputed value carries `imputed: true` + `imputed_from` (e.g. "neighbouring districts", "state median", "Earth Engine WorldPop", "Earth Engine rabi NDVI"). UI shows a small dotted outline on the map and an "estimated" tag on tiles; tooltip explains.
- "No data" remains only where nothing can be estimated (e.g. Lakshadweep rainfall); copy: "No estimate available for this district yet".

## Non‑goals this round
No new models, no new data sources beyond imputation inputs; keep the API contract; keep the planner and Methods content (restyled).

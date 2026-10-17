# Pitch — deck outline + 3‑minute video script (draft)

## Deck (10 slides)
1. **A record El Niño is forming right now.** CPC 8 Oct 2026: Niño‑3.4 +2.1 °C, 83 % chance of a historic event. Last strong El Niños (2002, 2009, 2015) cut India's monsoon 14‑22 % and foodgrain output 5‑8 %; child wasting spikes followed in rainfed districts.
2. **The gap.** Climate forecasts stop at rainfall. Crop statistics arrive 12‑18 months late. Nutrition surveys arrive every 4 years. Nobody connects them at the district level *before* the season.
3. **AnnaDrishti.** A standing season‑by‑season early‑warning system — Rabi and Kharif, every year — answering *Where will food security break, why, how much buffer do we have, and what should farmers plant?* El Niño 2026‑27 is simply the first season it runs on.
4. **Data fusion.** 11 public sources: IMD 0.25° gridded rainfall 2000‑25, DES/UPAG crop statistics 1997‑2025 (755 districts × 60 crops), NFHS‑4/5/6, Census + projections, PDS monthly offtake, FCI central pool stocks, ICRISAT 1966‑2017, NOAA ONI + IRI plume, Earth Engine (CHIRPS, MODIS NDVI, ERA5‑Land), **Google WeatherNext**.
5. **Method (honest).** ENSO‑conditioned analogs → district yield sensitivity (empirical, detrended) → exposure × sensitivity × capacity → risk with driver attribution. Hindcast on 2009/2014/2015/2023 shown in‑app.
6. **Gemini is the analyst.** Grounded on the district's evidence JSON: official briefing (who's at risk, 5 actions with lead times) + farmer advisory in Hindi/Marathi/Telugu (crop switch to millets/pulses, short‑duration varieties, sowing window). Function‑calling chat: "Which districts should pre‑position pulses?"
7. **Live demo** (screens).
8. **Architecture on Google Cloud.** Earth Engine → pipeline → Cloud Storage artifacts → Cloud Run (FastAPI + React) → Gemini API; Secret Manager; Cloud Build. Daily refresh job for live layers.
9. **Impact & users.** State food/agri/WCD departments, district collectors, FPOs, NGOs (Khushi Baby field network for last‑mile). Metric: lead time from months to a season; targets 100 M people in high‑risk districts.
10. **Next.** C3S seasonal ensembles, LightGBM yield model with spatial CV, FCI state stocks, ICAR contingency‑plan RAG on Vertex AI Search, WhatsApp farmer bot, Android field verification.

## Video script (≈170 s)
0‑15 s  Hook: ENSO chart + headline "Strongest El Niño on record may be forming." Voice: "In 2015 the last one left 330 districts drought‑hit. Which districts will it hurt next year, and what can we do *now*?"
15‑40 s  Map: switch scenario Neutral → El Niño; red spreads over Marathwada, Bundelkhand, Rayalaseema. KPI tiles change: people, children under 5.
40‑75 s  Click Nandurbar: risk 78, drivers (86 % rainfed, 31 % yield CV, stunting 48 %). Yield history with El Niño years shaded. Food balance + PDS dependency. Hindcast strip: "in 2015 we'd have scored it 74; actual yield fell 23 %."
75‑110 s Gemini briefing for officials; switch to Farmer card in Marathi; read 2 bullets.
110‑135 s Ask the map: "Which Maharashtra districts should pre‑position pulses stock?" → ranked list with chips.
135‑155 s Live layers: NDVI anomaly today + WeatherNext 10‑day rain. "Google's own weather model, inside the map."
155‑170 s Architecture flash + "Built on Google Cloud: Earth Engine, WeatherNext, Gemini, Cloud Run." Close on logo.

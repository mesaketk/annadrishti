# Submission checklist — Google Cloud AI Builder Cup 2026 (deadline 18 Oct 2026)

| Deliverable | Status | Where |
|---|---|---|
| Deployed prototype on Google Cloud | **Live** | https://annadrishti-801618653701.asia-south1.run.app (Cloud Run, asia-south1) |
| Public GitHub repository | pending — need repo URL, then `git push` | this folder (git initialised, nothing committed yet) |
| Demo video < 3 min | pending — record from script | docs/PITCH.md "Video script" (update: start on the role picker, show Farmer on phone, Officer briefing, Planner map + History, end on architecture) |
| Deck | **ready** | docs/AnnaDrishti_deck.pptx (fill team names on slide 1; GitHub + video URLs on slide 15) |

## Suggested form text
**Project name:** AnnaDrishti — season‑by‑season food‑security early warning for India's districts
**Theme:** Sustainability & Social Impact
**One‑liner:** Before every Rabi and Kharif, AnnaDrishti tells each of India's 753 districts how exposed its food system is, who will be hurt first, how much buffer the state holds, and what farmers should plant — grounded Gemini briefings per department and farmer advisories in nine languages with voice. This season's situation: a record El Niño.
**Google Cloud / AI used:** Gemini 3.8 Flash (grounded generation, function calling, personalised by profile/department), Gemini TTS, Earth Engine (CHIRPS, MODIS, ERA5‑Land, WorldPop, WeatherNext 2), BigQuery + BigQuery ML `AI.FORECAST` (TimesFM 2.5/3.0), Cloud Run, Artifact Registry, Secret Manager, Cloud Storage, Material Design 3.
**What's new vs existing tools:** connects climate outlook → district yield (ensemble validated out‑of‑sample) → food availability → nutrition → buffer stock → department actions; History mode replays 2003–2024; works every season, not only El Niño.

## Demo flow for the video (≈170 s)
1. Role picker → **Farmer** on phone: Nandurbar, Marathi, "Get advice", ▶ Listen (10 s of audio).
2. **District officer**: Kalahandi, department = WCD/ICDS → Overview traffic light → Why → Trends (El Niño years shaded) → Actions → Generate briefing.
3. **State planner**: Season Kharif 2027, scenario El Niño → map turns red; "What to prepare" table; Download CSV.
4. **History**: slide to 2015 → "The tool would have warned in 73 % of districts where the harvest fell".
5. Ask a question: "Which Maharashtra districts should pre‑position pulses first?"
6. Close on architecture slide: Earth Engine · BigQuery/TimesFM · Gemini · Cloud Run.

## After submission
- Rotate the Gemini key and the service‑account key; remove Owner‑level roles from the SA.
- Budget alert at $20; keep `--max-instances 5`.
- Monthly: `python3 pipeline/08_enso_status.py && python3 pipeline/04_risk.py && python3 pipeline/06_export.py && python3 pipeline/06b_history.py`, upload `artifacts/*.json` to the bucket, bounce the service.

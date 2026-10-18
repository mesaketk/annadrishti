import { useEffect } from 'react'
import { useStore } from '../lib/store'
import { fmtSigned } from '../lib/format'
import { globalModelsOf } from '../lib/models'
import { seasonsOf } from '../lib/scenario'
import { IconButton } from './ui'

const f2 = (v: number | null | undefined) => (v == null ? '–' : v.toFixed(2).replace('-', '−'))
const f1 = (v: number | null | undefined) => (v == null ? '–' : v.toFixed(1))

function H({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-1 mt-6 md-title-small text-primary">{children}</h3>
}

export default function MethodsModal({ onClose }: { onClose: () => void }) {
  const kpis = useStore((s) => s.kpis)
  const g = globalModelsOf(kpis)
  const outlook = kpis?.outlook
  const seasons = seasonsOf(kpis)
  const thr = kpis?.band_thresholds
  const sk = g?.skill, w = g?.weights, t = g?.timesfm
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-scrim/[0.32] p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Data and methods" onClick={(e) => e.stopPropagation()}
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-m3-xl bg-surface-container-high p-6 md-body-medium shadow-elev-3">
        <div className="flex items-start justify-between gap-3">
          <h2 className="md-headline-small">Data & methods</h2>
          <IconButton icon="close" label="Close" onClick={onClose} className="-mr-2 -mt-1" />
        </div>
        <p className="mt-2 rounded-m3-md bg-primary-container p-3 md-body-medium text-on-primary-container">
          <b>These are analog scenarios, not forecasts.</b> Each scenario asks &ldquo;what happened in comparable past years?&rdquo; and applies it to today&rsquo;s exposure and vulnerability.
        </p>

        <H>Data sources</H>
        <ul className="list-disc space-y-0.5 pl-5 text-muted">
          <li>Rainfall: IMD gridded JJAS anomalies; ENSO state from NOAA CPC (Niño-3.4 / ONI)</li>
          <li>Yields and crop mix: APY / UPAG district statistics; cost of cultivation and farm-gate prices (ICRISAT)</li>
          <li>Nutrition and capacity: NFHS-5 / NFHS-6, Poshan Tracker; PDS dependency</li>
          <li><b className="text-on-surface">Central pool grain stock (FCI, national)</b>: not district stock. It is the national reserve, shown with the months of ration supply it covers.</li>
          <li>Upcoming season rain: expected rain for the coming season versus normal, beyond the 10-day forecast, for the selected weather phase. A scenario, not a forecast.</li>
          <li>Colours: a colour-blind-safe palette (blue = low risk, amber = watch, vermilion = act now; orange = drier or worse, blue = wetter or better)</li>
          <li>Live signals: NDVI, CHIRPS and WeatherNext short-range rainfall; groundwater levels</li>
        </ul>

        <H>Seasons</H>
        <p className="text-muted">
          AnnaDrishti is a standing early-warning system: it is run <b className="text-on-surface">every season</b> and scores each district for the coming season under four ENSO phases (La Niña, Neutral, El Niño, Strong El Niño) plus a probability-weighted <i>Current outlook</i>.
          The ENSO outlook is refreshed monthly; El Niño 2026-27 is the current situation.
        </p>
        {seasons.length > 0 && (
          <table className="mt-2 w-full text-left md-body-medium">
            <thead className="md-label-medium text-mutedd"><tr><th className="py-1 font-medium">Season</th><th className="font-medium">Sowing</th><th className="font-medium">Harvest</th><th className="font-medium">Status</th></tr></thead>
            <tbody className="[&_td]:border-t [&_td]:border-outline-variant [&_td]:py-1">
              {seasons.map((s) => (
                <tr key={s.id}><td className="font-medium">{s.label}</td><td>{s.sowing?.replace('..', ' – ') ?? '–'}</td><td>{s.harvest ?? '–'}</td><td>{s.status ? s.status.replace(/_/g, ' ') : '–'}</td></tr>
              ))}
            </tbody>
          </table>
        )}
        {outlook?.enso?.p_by_season && (
          <p className="mt-2 md-body-small text-mutedd">
            ENSO phase probabilities{outlook.as_of ? ` (as of ${outlook.as_of})` : ''}:{' '}
            {seasons.map((s) => { const p = outlook.enso?.p_by_season?.[s.id]; return p ? `${s.label}: El Niño ${Math.round((p.elnino ?? 0) * 100)} % · Neutral ${Math.round((p.neutral ?? 0) * 100)} % · La Niña ${Math.round((p.lanina ?? 0) * 100)} %` : null }).filter(Boolean).join('; ')}.
          </p>
        )}
        {outlook?.refresh && (
          <p className="mt-1 md-body-small text-mutedd">
            Refresh cadence: {Object.entries(outlook.refresh).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v.replace(/\s*\(.*\)/, '')}`).join(' · ')}.
          </p>
        )}
        <p className="mt-1 md-body-small text-mutedd">
          Kharif exposure: JJAS rainfall anomaly, dry spells, onset, tmax. Rabi exposure: OND anomaly (residual soil moisture), Feb–Mar tmax (terminal heat), groundwater stress and the previous kharif deviation.
        </p>

        <H>Risk score</H>
        <p className="text-muted">
          score = 100 × (<b className="text-on-surface">0.45</b> · Exposure + <b className="text-on-surface">0.30</b> · Sensitivity + <b className="text-on-surface">0.25</b> · Adaptive-capacity deficit).
          Exposure is the scenario rainfall shock times district yield sensitivity (beta); sensitivity covers rainfed share, crop concentration, yield variability, small and marginal holdings and food self-sufficiency; capacity deficit covers child and women&rsquo;s nutrition, PDS dependency and climate vulnerability.
          Each component is rank-normalised, and a missing term is dropped and the rest reweighted, never imputed as zero.
        </p>

        <H>Bands</H>
        <p className="text-muted">
          {thr ? <>Low below <b className="text-on-surface">{f1(thr.low_below)}</b>, medium {f1(thr.low_below)}–{f1(thr.high_from)}, high from <b className="text-on-surface">{f1(thr.high_from)}</b>.</> : 'Bands are tertiles of the El Niño scenario.'}{' '}
          Thresholds are fixed from the El Niño scenario so that counts move with the selected scenario.
        </p>

        <H>Expected yield shock: ensemble</H>
        {g && (sk || w) ? (
          <>
            <p className="text-muted">
              The expected foodgrain yield shock is an ensemble of the ENSO-analog estimate and a LightGBM model
              {w?.analog != null && w?.lgbm != null && <>, weighted analog <b className="text-on-surface">{w.analog.toFixed(2)}</b> / LightGBM <b className="text-on-surface">{w.lgbm.toFixed(2)}</b> (inverse to out-of-sample MAE)</>}.
              The spread between the two is shown as ±spread in each district.
            </p>
            {sk && (
              <table className="mt-2 w-full text-left md-body-medium tabular-nums">
                <thead className="md-label-medium text-mutedd"><tr><th className="py-1 font-medium">Model</th><th className="font-medium">Out-of-sample ρ</th><th className="font-medium">MAE (pp)</th></tr></thead>
                <tbody className="[&_td]:border-t [&_td]:border-outline-variant [&_td]:py-1">
                  <tr><td>Analog (ENSO history)</td><td>{f2(sk.analogRho)}</td><td>{f1(sk.analogMae)}</td></tr>
                  <tr><td>LightGBM</td><td>{f2(sk.lgbmRho)}</td><td>{f1(sk.lgbmMae)}</td></tr>
                  <tr><td>Zero-shock baseline</td><td>–</td><td>{f1(sk.zeroMae)}</td></tr>
                </tbody>
              </table>
            )}
            <p className="mt-1 md-body-small text-mutedd">ρ is leave-year-out Spearman correlation between predicted shock and actual yield deviation (positive = good). TabFM was evaluated but not run (6.6 GB weights, CPU).</p>
          </>
        ) : <p className="text-muted">Ensemble skill table not available in this data release.</p>}

        <H>Hindcast</H>
        <p className="text-muted">
          For 2009, 2014, 2015 and 2023 the analog score is recomputed with data available before the year and compared with the actual yield deviation from trend; this is <b className="text-on-surface">in-sample</b> for the analog model (ρ: score vs loss, negative = good).
          The LightGBM hindcast is leave-year-out, hence out-of-sample (ρ: shock vs loss, positive = good).
          {kpis?.hindcast && <> Latest ρ (analog / LightGBM oos): {['2009', '2014', '2015', '2023'].filter((y) => kpis.hindcast?.[y]).map((y) => `${y} ${f2(kpis.hindcast![y].spearman_rho)} / ${f2(kpis.hindcast![y].rho_lgbm_oos)}`).join(' · ')}.</>}
        </p>

        <H>TimesFM caveat</H>
        <p className="text-muted">
          {t ? <>TimesFM 3.0 with an ONI covariate (BigQuery AI.FORECAST) projects JJAS 2027 rainfall at <b className="text-on-surface">{fmtSigned(t.anom ?? 0)} %</b>
            {t.p10 != null && t.p90 != null && <> [p10 {fmtSigned(t.p10, 0)}, p90 {fmtSigned(t.p90, 0)}]</>}. </> : 'TimesFM 3.0 with an ONI covariate (BigQuery AI.FORECAST) gives a national rainfall outlook. '}
          It is a national signal only and has no district-level skill (ρ≈0 vs history), so it is shown for context and does not feed the score.
        </p>
        {kpis?.method_note && <p className="mt-3 md-body-small text-mutedd">{kpis.method_note}</p>}
      </div>
    </div>
  )
}

"""07_bigquery.py - BigQuery warehouse + TimesFM (AI.FORECAST) forecasts for AnnaDrishti.

Reads  : artifacts/*.parquet, districts.json, kpis.json, timeseries/, _climate_cache/rain_{y}.npz (daily district rain),
         timeseries_social/, bq/*.sql
Writes : BigQuery dataset `annadrishti` (location asia-south1), GCS bucket `<project>-annadrishti` (artifacts/v1/),
         artifacts/_district_month_rain.parquet, artifacts/timesfm_forecasts.parquet, artifacts/timesfm_summary.parquet,
         artifacts/reports/07_bigquery_report.md
Auth   : GOOGLE_APPLICATION_CREDENTIALS (defaults to the git-ignored SA key in the project root). Key contents are never printed.
Run    : python3 pipeline/07_bigquery.py            (idempotent; WRITE_TRUNCATE everywhere; ~2 min after the rain cache exists)
         python3 pipeline/07_bigquery.py --skip-gcs
"""
from __future__ import annotations
import json, os, sys, time, warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import districts, oni as load_oni, ART, ROOT

ANALYSIS_ONLY = "--analysis-only" in sys.argv   # skip table loads + AI.FORECAST jobs; recompute summary/sanity/GCS/report
PROJECT = "aibuildercup-511905"
DATASET = "annadrishti"
LOCATION = "asia-south1"                 # AI.FORECAST (TimesFM 2.5 + 3.0) verified working here, incl. covariates
DS = f"{PROJECT}.{DATASET}"
BUCKET = f"{PROJECT}-annadrishti"
GCS_PREFIX = "artifacts/v1"
BQ_DIR = ROOT / "bq"
KEY = ROOT / "aibuildercup-511905-0689c9d7ac44.json"
if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ and KEY.exists():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(KEY)

from google.cloud import bigquery, storage

bq = bigquery.Client(project=PROJECT, location=LOCATION)
T0 = time.time()
JOB_STATS: list[dict] = []
LOG: list[str] = []

RAIN_LAST = "2025-12-01"                 # last observed IMD month in our cache
RAIN_END = "2027-09-01"                  # forecast horizon end (JJAS 2027 complete)
RAIN_H = 21                              # months from 2026-01 .. 2027-09
CTX = 320                                # TimesFM 3.0 context window (n*32); 312 monthly points available
POSHAN_H = 6
PDS_MAX_STALE_MONTHS = 12                # skip PDS forecast if latest observation older than this

# IRI/CPC plume (Sep-2026) for months beyond observed ONI. ASSUMPTIONS - approximate, decaying strong event.
# key = centre month of the 3-month season (e.g. OND -> Nov)
ONI_ASSUMED = {
    "2026-09": 2.20, "2026-10": 2.25,                       # ASO/SON: linear bridge from observed JAS 2.16 to OND 2.3
    "2026-11": 2.3, "2026-12": 2.4, "2027-01": 2.3, "2027-02": 2.0, "2027-03": 1.6, "2027-04": 1.2,
    "2027-05": 0.8, "2027-06": 0.5, "2027-07": 0.3, "2027-08": 0.1,
    "2027-09": 0.0,                                          # ASO27: extrapolated
}
SEAS_CENTRE = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6, "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}
HINDCAST_YEARS = [2009, 2015, 2023, 2025]


def log(*a):
    s = " ".join(str(x) for x in a)
    print(f"[{time.time() - T0:6.1f}s] {s}", flush=True)
    LOG.append(s)


# ── helpers ───────────────────────────────────────────────────────────────────
def bq_type(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s): return "BOOL"
    if pd.api.types.is_integer_dtype(s): return "INT64"
    if pd.api.types.is_float_dtype(s): return "FLOAT64"
    return "STRING"


def prep(df: pd.DataFrame, date_cols=()) -> tuple[pd.DataFrame, list[bigquery.SchemaField]]:
    df = df.copy()
    schema = []
    for c in df.columns:
        if c in date_cols:
            df[c] = pd.to_datetime(df[c]).dt.date
            schema.append(bigquery.SchemaField(c, "DATE")); continue
        t = bq_type(df[c])
        if t == "FLOAT64": df[c] = df[c].astype("float64")
        elif t == "STRING":
            df[c] = df[c].astype(object).where(df[c].notna(), None)
            df[c] = df[c].map(lambda v: None if v is None else str(v))
        # lgd is the key: force INT64
        if c == "lgd": t = "INT64"
        schema.append(bigquery.SchemaField(c, t, mode="REQUIRED" if c == "lgd" else "NULLABLE"))
    return df, schema


def load(name: str, df: pd.DataFrame, date_cols=()):
    df, schema = prep(df, date_cols)
    cfg = bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE")
    j = bq.load_table_from_dataframe(df, f"{DS}.{name}", job_config=cfg, location=LOCATION)
    j.result()
    t = bq.get_table(f"{DS}.{name}")
    log(f"loaded {name:<26} rows={t.num_rows:>8,} bytes={t.num_bytes:>11,}")


def run_sql(fname: str, params: dict, dest: str | None = None, append=False) -> pd.DataFrame | None:
    if ANALYSIS_ONLY:
        return None
    sql = (BQ_DIR / fname).read_text()
    for k, v in {"DS": DS, **params}.items():
        sql = sql.replace("${" + k + "}", str(v))
    cfg = bigquery.QueryJobConfig()
    if dest:
        cfg.destination = f"{DS}.{dest}"
        cfg.write_disposition = "WRITE_APPEND" if append else "WRITE_TRUNCATE"
    job = bq.query(sql, job_config=cfg, location=LOCATION)
    job.result()
    JOB_STATS.append(dict(sql=fname, dest=dest, params=json_safe(params), bytes_processed=job.total_bytes_processed,
                          bytes_billed=job.total_bytes_billed, slot_ms=job.slot_millis,
                          secs=round((job.ended - job.started).total_seconds(), 1)))
    s = JOB_STATS[-1]
    log(f"query {fname} -> {dest} bytes_processed={s['bytes_processed']:,} slot_ms={s['slot_ms']:,} secs={s['secs']}")
    return None


STATS_CACHE = ART / "_bq_jobstats.json"


def json_safe(d):
    return {k: str(v) for k, v in d.items()}


def read(sql: str) -> pd.DataFrame:
    return bq.query(sql.replace("${DS}", DS), location=LOCATION).to_dataframe(create_bqstorage_client=False)


# ── 1. warehouse tables ───────────────────────────────────────────────────────
def ensure_dataset():
    ds = bigquery.Dataset(DS)
    ds.location = LOCATION
    ds.description = "AnnaDrishti: district climate / crops / nutrition / risk warehouse + TimesFM forecasts"
    bq.create_dataset(ds, exists_ok=True)
    got = bq.get_dataset(DS)
    assert got.location == LOCATION, f"dataset exists in {got.location}, expected {LOCATION}"
    log(f"dataset {DS} location={got.location}")


def risk_flat() -> pd.DataFrame:
    D = json.load(open(ART / "districts.json"))
    rows = []
    for d in D:
        r = dict(lgd=d["lgd"], district=d["district"], state=d["state"], main_season=d.get("main_season"),
                 beta_source=d.get("beta_source"), population_2026=d.get("population_2026"),
                 children_u5_est=d.get("children_u5_est"))
        for k, v in (d.get("food_balance") or {}).items():
            r[f"fb_{k}"] = v
        for rd in ("nfhs5", "nfhs6"):
            n = (d.get("nutrition") or {}).get(rd) or {}
            for k in ("stunting", "wasting", "underweight", "child_anaemia", "women_anaemia"):
                r[f"{rd}_{k}"] = n.get(k)
        pl = (d.get("nutrition") or {}).get("poshan_live") or {}
        r["poshan_underweight_pct"] = pl.get("underweight_pct"); r["poshan_stunted_pct"] = pl.get("stunted_pct")
        for s in ("neutral", "elnino", "elnino_strong"):
            x = (d.get("risk") or {}).get(s) or {}
            for k in ("score", "band", "expected_yield_shock_pct", "exposure", "sensitivity", "capacity", "rain_anomaly_pct"):
                r[f"{s}_{k}"] = x.get(k)
            a = x.get("actions") or {}
            r[f"{s}_grain_preposition_t"] = a.get("grain_preposition_t")
            r[f"{s}_priority_rank_national"] = a.get("priority_rank_national")
        rows.append(r)
    df = pd.DataFrame(rows)
    for c in df.columns:
        if c.endswith("priority_rank_national") or c in ("population_2026", "children_u5_est"):
            df[c] = df[c].astype("Int64")
    return df


def load_core_tables():
    m = districts()
    load("districts", m)
    load("crops_district_year", pd.read_parquet(ART / "crops_district_year.parquet"))
    load("crops_latest", pd.read_parquet(ART / "crops_latest.parquet"))
    load("climate_district", pd.read_parquet(ART / "climate_district.parquet"))
    load("social_district", pd.read_parquet(ART / "social_district.parquet"))
    load("extra_district", pd.read_parquet(ART / "extra_district.parquet"))
    load("yield_sensitivity", pd.read_parquet(ART / "yield_sensitivity.parquet"))
    load("risk_district", risk_flat())
    load("actions_elnino", pd.read_csv(ART / "actions_elnino.csv"))


# ── 2. monthly series ─────────────────────────────────────────────────────────
def build_rain_monthly() -> pd.DataFrame:
    cache = ART / "_district_month_rain.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    lg = districts().lgd.values       # same ordering 02_climate.py used for the daily cache
    frames = []
    for y in range(2000, 2026):
        z = np.load(ART / "_climate_cache" / f"rain_{y}.npz", allow_pickle=True)
        d, t = z["daily"], pd.to_datetime(z["time"])
        assert d.shape[0] == len(lg)
        for mth in range(1, 13):
            sel = np.asarray(t.month == mth)
            s = d[:, sel].sum(1)                          # NaN day => NaN month (only the 4 null districts)
            frames.append(pd.DataFrame({"lgd": lg, "month": pd.Timestamp(y, mth, 1), "rain_mm": s.astype("float64")}))
    out = pd.concat(frames, ignore_index=True).dropna(subset=["rain_mm"])
    out["rain_mm"] = out.rain_mm.round(2)
    out.to_parquet(cache)
    return out


def build_oni_monthly() -> pd.DataFrame:
    o = load_oni()
    o = o[o.seas.isin(SEAS_CENTRE)].copy()
    o["month"] = [pd.Timestamp(int(y), SEAS_CENTRE[s], 1) for s, y in zip(o.seas, o.yr)]
    obs = o[(o.month >= "2000-01-01")][["month", "anom"]].rename(columns={"anom": "oni"})
    obs["source"] = "observed_noaa_cpc"
    last = obs.month.max()
    ass = pd.DataFrame([{"month": pd.Timestamp(k + "-01"), "oni": v, "source": "assumed_iri_plume"}
                        for k, v in ONI_ASSUMED.items() if pd.Timestamp(k + "-01") > last])
    out = pd.concat([obs, ass], ignore_index=True).drop_duplicates("month").sort_values("month").reset_index(drop=True)
    full = pd.date_range("2000-01-01", RAIN_END, freq="MS")
    assert set(full) == set(out.month), f"ONI months missing: {sorted(set(full) - set(out.month))[:5]}"
    return out


def build_poshan_monthly() -> pd.DataFrame:
    e = pd.read_parquet(ART / "extra_district.parquet")
    rows = []
    for lgd, j in zip(e.lgd, e.poshan_series_json):
        if not isinstance(j, str): continue
        s = pd.Series(json.loads(j))
        s.index = pd.to_datetime(s.index + "-01")
        s = s.sort_index().astype(float)
        full = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="MS"))
        filled = full.interpolate(limit_area="inside")
        for mth, v in full.items():
            rows.append((int(lgd), mth, None if np.isnan(v) else v, float(filled[mth]), bool(np.isnan(v))))
    return pd.DataFrame(rows, columns=["lgd", "month", "underweight_pct", "underweight_pct_filled", "is_interpolated"])


def build_pds_monthly() -> pd.DataFrame:
    rows = []
    for f in (ART / "timeseries_social").glob("*.json"):
        for r in json.load(open(f)).get("pds_monthly", []):
            rows.append((int(f.stem), pd.Timestamp(r["date"]), r.get("rice_t"), r.get("wheat_t"),
                         r.get("rice_alloc_t"), r.get("wheat_alloc_t")))
    df = pd.DataFrame(rows, columns=["lgd", "month", "rice_t", "wheat_t", "rice_alloc_t", "wheat_alloc_t"])
    return df.sort_values(["lgd", "month"]).reset_index(drop=True)


def load_series_tables():
    rain = build_rain_monthly()
    load("district_month_rain", rain, date_cols=("month",))
    oni = build_oni_monthly()
    load("district_month_oni", oni, date_cols=("month",))
    po = build_poshan_monthly()
    load("district_month_poshan", po, date_cols=("month",))
    pds = build_pds_monthly()
    load("district_month_pds", pds, date_cols=("month",))
    return rain, oni, po, pds


# ── 3. forecasts ──────────────────────────────────────────────────────────────
def run_forecasts(pds: pd.DataFrame, po: pd.DataFrame) -> dict:
    """With --analysis-only run_sql() is a no-op (forecast tables already materialised; job stats come from cache)."""
    notes = {}
    # (a) rain, production
    run_sql("01_rain_univariate.sql", dict(CUTOFF=RAIN_LAST, H=RAIN_H), "forecast_rain_timesfm")
    run_sql("02_rain_covariate.sql", dict(CUTOFF=RAIN_LAST, END=RAIN_END, H=RAIN_H, CTX=CTX), "forecast_rain_timesfm", append=True)
    # hindcasts (history through Dec of y-1, 12 months ahead, ONI covariate uses ACTUAL ONI = perfect-ENSO-forecast upper bound)
    for i, y in enumerate(HINDCAST_YEARS):
        cut, end = f"{y - 1}-12-01", f"{y}-12-01"
        run_sql("01_rain_univariate.sql", dict(CUTOFF=cut, H=12), "backtest_rain_timesfm", append=i > 0)
        run_sql("02_rain_covariate.sql", dict(CUTOFF=cut, END=end, H=12, CTX=CTX), "backtest_rain_timesfm", append=True)
    # (b) poshan
    last = po.month.max()
    reporters = po.groupby("lgd").month.max()
    last_common = reporters.mode().iloc[0]
    notes["poshan_cutoff"] = str(last_common.date()); notes["poshan_n_series"] = int((reporters == last_common).sum())
    run_sql("03_poshan.sql", dict(LAST=last_common.date(), H=POSHAN_H), "forecast_poshan_timesfm")
    # (c) PDS
    stale = (pd.Timestamp("2026-10-01").to_period("M") - pds.month.max().to_period("M")).n
    notes["pds_last_month"] = str(pds.month.max().date()); notes["pds_stale_months"] = int(stale)
    notes["pds_forecast_run"] = stale <= PDS_MAX_STALE_MONTHS
    if notes["pds_forecast_run"]:
        run_sql("04_pds.sql", dict(LAST=pds.month.max().date(), H=12), "forecast_pds_timesfm")
    else:
        log(f"PDS forecast SKIPPED: latest observation {notes['pds_last_month']} is {stale} months stale (> {PDS_MAX_STALE_MONTHS})")
    return notes


def jjas_stats(f: pd.DataFrame, year: int, normal: pd.Series) -> pd.DataFrame:
    """Per-lgd JJAS total + anomaly vs 2000-24 normal. p10/p90 of the total from monthly 80% intervals,
    assuming independent monthly errors (sd_m = (p90-p10)/(2*1.2816)); this is an approximation."""
    z = 1.2815516
    g = f[(f.horizon_month >= f"{year}-06-01") & (f.horizon_month <= f"{year}-09-01")].copy()
    g["sd"] = (g.p90 - g.p10) / (2 * z)
    a = g.groupby("lgd").agg(n=("forecast", "size"), tot=("forecast", "sum"), var=("sd", lambda s: float((s ** 2).sum())))
    a = a[a.n == 4]
    a["lo"] = (a.tot - z * np.sqrt(a["var"])).clip(lower=0)
    a["hi"] = a.tot + z * np.sqrt(a["var"])
    nm = normal.reindex(a.index)
    out = pd.DataFrame({"fc_mm": a.tot, "anom_pct": (a.tot - nm) / nm * 100,
                        "p10_pct": (a.lo - nm) / nm * 100, "p90_pct": (a.hi - nm) / nm * 100})
    return out


def assemble(notes: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    m = districts()
    clim = pd.read_parquet(ART / "climate_district.parquet").set_index("lgd")
    normal = clim.jjas_normal_mm.astype("float64")
    fr = read("SELECT * FROM `${DS}.forecast_rain_timesfm`")
    fp = read("SELECT * FROM `${DS}.forecast_poshan_timesfm`")
    for d in (fr, fp):
        d["horizon_month"] = pd.to_datetime(d.horizon_month)
    bad = pd.concat([fr, fp]).status.fillna("").str.len().gt(0).sum()
    notes["non_empty_status_rows"] = int(bad)
    fall = pd.concat([fr, fp], ignore_index=True)
    fall = fall.rename(columns={})[["lgd", "series", "variant", "horizon_month", "forecast", "p10", "p90"]]
    fall["horizon_month"] = fall.horizon_month.dt.date
    fall.to_parquet(ART / "timesfm_forecasts.parquet", index=False)

    uni = fr[fr.variant == "timesfm2.5_univariate"]; cov = fr[fr.variant == "timesfm3.0_oni_covariate"]
    su, sc = jjas_stats(uni, 2027, normal), jjas_stats(cov, 2027, normal)
    ps = fp.sort_values("horizon_month")
    last_obs = read("SELECT lgd, ARRAY_AGG(underweight_pct_filled ORDER BY month DESC LIMIT 1)[OFFSET(0)] AS last_obs "
                                                 "FROM `${DS}.district_month_poshan` GROUP BY lgd").set_index("lgd").last_obs
    p6 = ps.groupby("lgd").forecast.last()
    summ = pd.DataFrame({"lgd": m.lgd.values}).set_index("lgd")
    # primary = ONI-covariate variant (TimesFM 3.0, ENSO-aware); *_uni = univariate TimesFM 2.5
    summ["jjas2027_forecast_mm"] = sc.fc_mm; summ["jjas2027_anom_pct"] = sc.anom_pct
    summ["jjas2027_p10_pct"] = sc.p10_pct; summ["jjas2027_p90_pct"] = sc.p90_pct
    summ["jjas2027_forecast_mm_uni"] = su.fc_mm; summ["jjas2027_anom_pct_uni"] = su.anom_pct
    summ["jjas2027_p10_pct_uni"] = su.p10_pct; summ["jjas2027_p90_pct_uni"] = su.p90_pct
    summ["poshan_6m_forecast_pct"] = p6
    summ["poshan_trend_pp"] = p6 - last_obs.reindex(p6.index)
    summ["pds_12m_forecast_t"] = np.nan
    if notes.get("pds_forecast_run"):
        fd = read("SELECT lgd, SUM(forecast) t FROM `${DS}.forecast_pds_timesfm` GROUP BY lgd").set_index("lgd").t
        summ["pds_12m_forecast_t"] = fd
    summ = summ.reset_index()
    summ.to_parquet(ART / "timesfm_summary.parquet", index=False)
    load("timesfm_summary", summ)
    return fall, summ, dict(normal=normal, uni=su, cov=sc)


# ── 4. sanity ─────────────────────────────────────────────────────────────────
def sanity(summ: pd.DataFrame, parts: dict) -> dict:
    cl = pd.read_parquet(ART / "climate_district.parquet").set_index("lgd")
    cr = pd.read_parquet(ART / "crops_latest.parquet").set_index("lgd")
    w = cr.gross_cropped_area_ha.reindex(summ.lgd).values
    s = summ.set_index("lgd")
    out = {}
    for tag, col in (("covariate", "jjas2027_anom_pct"), ("univariate", "jjas2027_anom_pct_uni")):
        x = s[col]; ok = x.notna()
        ww = pd.Series(w, index=s.index)[ok]
        out[tag] = dict(n=int(ok.sum()), mean=float(x.mean()), area_wtd_mean=float(np.average(x[ok], weights=ww.fillna(ww.mean()))),
                        pct=x.quantile([0, .05, .1, .25, .5, .75, .9, .95, 1]).round(2).to_dict(),
                        frac_below_minus10=float((x < -10).mean()), frac_deficit=float((x < 0).mean()),
                        p10_p90_width_median=float((s["jjas2027_p90_pct" + ("" if tag == "covariate" else "_uni")] -
                                                    s["jjas2027_p10_pct" + ("" if tag == "covariate" else "_uni")]).median()))
        for ref in ("elnino_mean_anomaly_pct", "strong_elnino_anomaly_pct"):
            y = cl[ref].reindex(s.index); k = x.notna() & y.notna()
            out[tag][f"pearson_vs_{ref}"] = float(np.corrcoef(x[k], y[k])[0, 1])
            out[tag][f"spearman_vs_{ref}"] = float(x[k].rank().corr(y[k].rank()))
        out[tag]["analog_elnino_mean"] = float(cl.elnino_mean_anomaly_pct.reindex(s.index)[ok].mean())
        out[tag]["analog_strong_mean"] = float(cl.strong_elnino_anomaly_pct.reindex(s.index)[ok].mean())
    # monthly climatology check: JJAS normal from monthly table vs climate_district
    rain = pd.read_parquet(ART / "_district_month_rain.parquet")
    j = rain[(rain.month.dt.month.between(6, 9)) & (rain.month.dt.year <= 2024)].groupby("lgd").rain_mm.sum() / 25
    k = j.index.intersection(cl.index)
    out["monthly_vs_jjas_normal_maxabs_pct"] = float(((j[k] - cl.jjas_normal_mm[k]).abs() / cl.jjas_normal_mm[k] * 100).max())
    # hindcasts
    bt = read("SELECT * FROM `${DS}.backtest_rain_timesfm`"); bt["horizon_month"] = pd.to_datetime(bt.horizon_month)
    bt["cutoff"] = pd.to_datetime(bt.cutoff)
    actual = rain[rain.month.dt.month.between(6, 9)].copy(); actual["year"] = actual.month.dt.year
    act = actual.groupby(["year", "lgd"]).rain_mm.sum()
    normal = parts["normal"]
    hc = []
    for y in HINDCAST_YEARS:
        a = act.loc[y]; an = (a - normal.reindex(a.index)) / normal.reindex(a.index) * 100
        row = dict(year=y, actual_allindia_mean_anom=float(an.mean()))
        for v, tag in (("timesfm2.5_univariate", "uni"), ("timesfm3.0_oni_covariate", "cov")):
            f = bt[(bt.variant == v) & (bt.cutoff == pd.Timestamp(f"{y - 1}-12-01"))]
            st = jjas_stats(f, y, normal)
            k = st.index.intersection(an.index)
            row[f"{tag}_mean_anom"] = float(st.anom_pct[k].mean())
            row[f"{tag}_corr"] = float(np.corrcoef(st.anom_pct[k], an[k])[0, 1])
            row[f"{tag}_rmse"] = float(np.sqrt(((st.anom_pct[k] - an[k]) ** 2).mean()))
        row["climatology_rmse"] = float(np.sqrt((an ** 2).mean()))        # forecasting 0% anomaly
        hc.append(row)
    out["hindcast"] = hc
    return out


# ── 5. GCS ────────────────────────────────────────────────────────────────────
def upload_gcs():
    try:
        return _upload_gcs()
    except Exception as e:                     # e.g. 403 billing disabled: BigQuery sandbox works without billing, GCS does not
        msg = str(e).split("\n")[0][:300]
        log(f"GCS upload FAILED (non-fatal): {type(e).__name__}: {msg}")
        return dict(error=msg)


def _upload_gcs():
    sc = storage.Client(project=PROJECT)
    b = sc.lookup_bucket(BUCKET)
    if b is None:
        b = sc.bucket(BUCKET)
        b.iam_configuration.uniform_bucket_level_access_enabled = True
        b.iam_configuration.public_access_prevention = "enforced"
        b = sc.create_bucket(b, location=LOCATION)
        log(f"created bucket {BUCKET} in {b.location}")
    else:
        b.iam_configuration.uniform_bucket_level_access_enabled = True
        b.iam_configuration.public_access_prevention = "enforced"
        b.patch()
    files = [(ART / "districts.json", f"{GCS_PREFIX}/districts.json"), (ART / "kpis.json", f"{GCS_PREFIX}/kpis.json")]
    files += [(p, f"{GCS_PREFIX}/timeseries/{p.name}") for p in sorted((ART / "timeseries").glob("*.json"))]

    def up(a):
        p, k = a
        b.blob(k).upload_from_filename(str(p), content_type="application/json")
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(up, files))
    n = sum(1 for _ in sc.list_blobs(BUCKET, prefix=GCS_PREFIX + "/"))
    b.reload()
    log(f"gcs gs://{BUCKET}/{GCS_PREFIX}/ objects={n} uniform_access={b.iam_configuration.uniform_bucket_level_access_enabled} "
        f"public_access_prevention={b.iam_configuration.public_access_prevention} location={b.location}")
    return dict(objects=n, location=b.location, pap=b.iam_configuration.public_access_prevention)


# ── report ────────────────────────────────────────────────────────────────────
def write_report(notes, san, gcs):
    tabs = sorted(bq.list_tables(DS), key=lambda t: t.table_id)
    rows = []
    for t in tabs:
        tt = bq.get_table(t.reference)
        rows.append(f"| `{tt.table_id}` | {tt.num_rows:,} | {tt.num_bytes:,} |")
    tb = sum(j["bytes_processed"] or 0 for j in JOB_STATS); ts = sum(j["slot_ms"] or 0 for j in JOB_STATS)
    jr = [f"| {j['sql']} | {j['dest']} | {j['params'].get('CUTOFF', j['params'].get('LAST', ''))} | {j['bytes_processed']:,} | {j['slot_ms']:,} | {j['secs']} |" for j in JOB_STATS]
    c, u = san["covariate"], san["univariate"]
    def blk(t, d):
        return [f"**{t}** (n={d['n']} districts)",
                f"- mean anomaly {d['mean']:+.2f}% (cropped-area-weighted {d['area_wtd_mean']:+.2f}%); share of districts with deficit {d['frac_deficit']:.0%}; share below -10%: {d['frac_below_minus10']:.0%}",
                f"- percentiles (0/5/10/25/50/75/90/95/100): " + ", ".join(f"{v:+.1f}" for v in d["pct"].values()),
                f"- median 80% interval width on the anomaly: {d['p10_p90_width_median']:.1f} pp",
                f"- vs district analog El Nino mean anomaly (mean {d['analog_elnino_mean']:+.1f}%): Pearson {d['pearson_vs_elnino_mean_anomaly_pct']:+.2f}, Spearman {d['spearman_vs_elnino_mean_anomaly_pct']:+.2f}",
                f"- vs strong-El Nino analog (2002/09/15; mean {d['analog_strong_mean']:+.1f}%): Pearson {d['pearson_vs_strong_elnino_anomaly_pct']:+.2f}, Spearman {d['spearman_vs_strong_elnino_anomaly_pct']:+.2f}", ""]
    hc = ["| JJAS year | actual all-India mean anom % | uni fc mean % | uni corr | uni RMSE | ONI-cov fc mean % | cov corr | cov RMSE | climatology RMSE |", "|---|---|---|---|---|---|---|---|---|"]
    for r in san["hindcast"]:
        hc.append(f"| {r['year']} | {r['actual_allindia_mean_anom']:+.1f} | {r['uni_mean_anom']:+.1f} | {r['uni_corr']:+.2f} | {r['uni_rmse']:.1f} | {r['cov_mean_anom']:+.1f} | {r['cov_corr']:+.2f} | {r['cov_rmse']:.1f} | {r['climatology_rmse']:.1f} |")
    md = ["# 07 - BigQuery warehouse + TimesFM forecasts", "",
          f"Project `{PROJECT}`, dataset `{DS}`, **location `{LOCATION}`** (AI.FORECAST verified in asia-south1 and US). "
          + (f"GCS: `gs://{BUCKET}/{GCS_PREFIX}/` ({gcs['objects']} objects, uniform bucket-level access, public access prevention enforced)." if gcs.get("objects") else f"GCS: **not uploaded** ({gcs.get('error', 'skipped')}). Re-run `python3 pipeline/07_bigquery.py --analysis-only` once billing is enabled."), "",
          "## Tables", "", "| table | rows | bytes |", "|---|---|---|", *rows, "",
          "## Models and syntax", "",
          "- `AI.FORECAST` (BigQuery AI function, no model object to create). Univariate: `model => 'TimesFM 2.5'` (default, GA), `data_col`, `timestamp_col`, `id_cols => ['lgd']`, `horizon`, `confidence_level => 0.8`.",
          f"- Covariates: **supported only via TimesFM 3.0 (Preview) multivariate form**: `target_cols => ['rain_mm']`, `future_covariate_cols => ['oni']`, `model => 'TimesFM 3.0'`, `context_window => {CTX}`; future target rows must be NULL and the covariate must span history + horizon. TimesFM 2.5 has no covariate support.",
          f"- Rain horizon is **{RAIN_H} months** (2026-01..2027-09) because IMD data in the cache ends 2025-12 (the brief said 15; 21 is what reaches 2027-09). 2026 is unobserved rainfall, forecast through.",
          "- ONI covariate: observed NOAA CPC ONI through JAS-2026 (centre month 2026-08); later months are **assumptions** approximating the IRI/CPC plume of a strong event decaying: "
          + ", ".join(f"{k} {v}" for k, v in ONI_ASSUMED.items()) + ". Season-to-month mapping uses the centre month (OND -> Nov).",
          "- Primary summary columns (`jjas2027_*`) use the **ONI-covariate (TimesFM 3.0) variant**; `*_uni` columns hold the univariate TimesFM 2.5 result. Both variants are in `forecast_rain_timesfm` (column `variant`).",
          "- JJAS p10/p90: the model gives 80% bounds per month; for the 4-month total we combine monthly sds assuming independent errors (approximation, likely too narrow if monthly errors correlate).", "",
          "## Forecast sanity (JJAS 2027 anomaly vs 2000-24 normal)", "",
          *blk("ONI-covariate (TimesFM 3.0, primary)", c), *blk("Univariate (TimesFM 2.5)", u),
          f"Monthly table vs `climate_district.jjas_normal_mm`: max abs deviation {san['monthly_vs_jjas_normal_maxabs_pct']:.3f}% (consistency check).", "",
          "### Hindcasts (history through Dec of year-1, 12 months ahead; ONI covariate uses ACTUAL ONI = perfect-ENSO-forecast upper bound)", "", *hc, "",
          "## Poshan / PDS", "",
          f"- Poshan underweight %: {notes['poshan_n_series']} districts with series ending {notes['poshan_cutoff']}; 6-month horizon; internal gaps linearly interpolated (flag `is_interpolated`). Series are only ~24 monthly points and integer-rounded: treat as indicative.",
          f"- PDS: latest observation {notes['pds_last_month']} ({notes['pds_stale_months']} months stale) -> forecast {'run' if notes['pds_forecast_run'] else '**skipped**'}; `pds_12m_forecast_t` is null. Template `bq/04_pds.sql` kept.",
          f"- Rows with non-empty `ai_forecast_status`: {notes['non_empty_status_rows']}.", "",
          "## Caveats", "",
          "- **BigQuery sandbox**: project has no billing account (GCS bucket creation returns 403 'billing account ... disabled'). BigQuery works in sandbox mode but all tables auto-expire after 60 days (first expiry 2026-12-16; cannot be lifted without billing). Re-running this script refreshes them. Enable billing to lift the expiry and to create the GCS bucket.",
          "- **Low-bias of median forecasts**: `forecast_value` is the 50% quantile. Monthly rainfall is right-skewed, so the sum of four monthly medians sits below the mean-based normal. Hindcasts show a persistent negative bias (all-India mean anomaly forecasts of -10..-20% even when actual was +11%). Read the absolute JJAS-2027 anomalies as biased low by roughly 5-10 pp; use them as a relative/ranking signal at most, and see the hindcast table for how little district-level skill there is.",
          "- District-level skill is approximately nil: hindcast correlation of forecast vs actual JJAS anomaly across districts is between -0.06 and +0.26 and district RMSE is not better than forecasting 0% (climatology). The ONI covariate shifts the all-India mean towards deficit but does not add spatial skill. TimesFM output is a pattern forecast; it does not replace the ENSO-conditioned analog scenarios in 04_risk.py.",
          "- TimesFM 3.0 multivariate is Preview (billing/feature changes possible; token billing from 2026-12-01).",
          "- ONI beyond JAS-2026 is an assumption (see above), not an official forecast.", "",
          "## Cost", "", f"Total bytes processed {tb:,} ({tb / 1e6:.1f} MB); total slot-ms {ts:,}. On-demand at ~$6.25/TiB that is far below one cent; AI.FORECAST bills at the BigQuery ML prediction rate (see pricing page; TimesFM 3.0 Preview token billing starts 2026-12-01).", "",
          "| sql | dest | cutoff | bytes processed | slot ms | secs |", "|---|---|---|---|---|---|", *jr, ""]
    (ART / "reports").mkdir(exist_ok=True)
    (ART / "reports" / "07_bigquery_report.md").write_text("\n".join(md))
    return tb, ts


def main():
    skip_gcs = "--skip-gcs" in sys.argv
    ensure_dataset()
    if ANALYSIS_ONLY:
        JOB_STATS.extend(json.load(open(STATS_CACHE)))
        po, pds = build_poshan_monthly(), build_pds_monthly()
    else:
        load_core_tables()
        rain, oni, po, pds = load_series_tables()
    notes = run_forecasts(pds, po)
    if not ANALYSIS_ONLY:
        json.dump(JOB_STATS, open(STATS_CACHE, "w"), default=str)
    fall, summ, parts = assemble(notes)
    san = sanity(summ, parts)
    gcs = {} if skip_gcs else upload_gcs()
    tb, ts = write_report(notes, san, gcs)
    log(f"TOTAL bytes_processed={tb:,} slot_ms={ts:,}")
    print(json.dumps(san, indent=1, default=float))


if __name__ == "__main__":
    main()

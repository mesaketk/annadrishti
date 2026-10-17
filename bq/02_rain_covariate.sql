-- TimesFM 3.0 (Preview) multivariate: rain_mm target + ONI as FUTURE covariate (known/assumed through ${END}).
-- Future target rows are NULL. Params: ${DS} ${CUTOFF} ${END} ${H} ${CTX} (H = months between CUTOFF and END; must be a literal)
WITH ids AS (
  SELECT DISTINCT lgd FROM `${DS}.district_month_rain`
),
spine AS (
  SELECT lgd, m AS month
  FROM ids, UNNEST(GENERATE_DATE_ARRAY(DATE '2000-01-01', DATE '${END}', INTERVAL 1 MONTH)) AS m
),
input AS (
  SELECT s.lgd, s.month,
         IF(s.month <= DATE '${CUTOFF}', r.rain_mm, NULL) AS rain_mm,
         o.oni
  FROM spine s
  LEFT JOIN `${DS}.district_month_rain` r USING (lgd, month)
  JOIN `${DS}.district_month_oni` o USING (month)
)
SELECT
  lgd,
  'rain_mm' AS series,
  'timesfm3.0_oni_covariate' AS variant,
  DATE '${CUTOFF}' AS cutoff,
  DATE(month) AS horizon_month,
  rain_mm.value AS forecast,
  rain_mm.prediction_interval_lower_bound AS p10,
  rain_mm.prediction_interval_upper_bound AS p90,
  ai_forecast_status AS status
FROM AI.FORECAST(
  TABLE input,
  target_cols => ['rain_mm'],
  timestamp_col => 'month',
  id_cols => ['lgd'],
  horizon => ${H},
  confidence_level => 0.8,
  context_window => ${CTX},
  future_covariate_cols => ['oni'],
  model => 'TimesFM 3.0'
)
WHERE time_series_type = 'forecast'

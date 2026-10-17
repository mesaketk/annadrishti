-- TimesFM 2.5 (GA), univariate monthly rainfall per district. Params: ${DS} ${CUTOFF} ${H}
SELECT
  lgd,
  'rain_mm' AS series,
  'timesfm2.5_univariate' AS variant,
  DATE '${CUTOFF}' AS cutoff,
  DATE(forecast_timestamp) AS horizon_month,
  forecast_value AS forecast,
  prediction_interval_lower_bound AS p10,   -- confidence_level 0.8 => 10th..90th percentile
  prediction_interval_upper_bound AS p90,
  ai_forecast_status AS status
FROM AI.FORECAST(
  (SELECT lgd, month, rain_mm FROM `${DS}.district_month_rain` WHERE month <= DATE '${CUTOFF}'),
  data_col => 'rain_mm',
  timestamp_col => 'month',
  id_cols => ['lgd'],
  horizon => ${H},
  confidence_level => 0.8,
  model => 'TimesFM 2.5'
)

-- TimesFM 2.5 univariate, Poshan Tracker underweight % (gap-filled monthly), 6 months ahead.
-- Only districts whose series reaches the latest reporting month. Params: ${DS} ${LAST} ${H}
SELECT
  lgd,
  'poshan_underweight_pct' AS series,
  'timesfm2.5_univariate' AS variant,
  DATE '${LAST}' AS cutoff,
  DATE(forecast_timestamp) AS horizon_month,
  forecast_value AS forecast,
  prediction_interval_lower_bound AS p10,
  prediction_interval_upper_bound AS p90,
  ai_forecast_status AS status
FROM AI.FORECAST(
  (SELECT lgd, month, underweight_pct_filled AS v
   FROM `${DS}.district_month_poshan`
   WHERE lgd IN (SELECT lgd FROM `${DS}.district_month_poshan` GROUP BY lgd HAVING MAX(month) = DATE '${LAST}')),
  data_col => 'v',
  timestamp_col => 'month',
  id_cols => ['lgd'],
  horizon => ${H},
  confidence_level => 0.8,
  model => 'TimesFM 2.5'
)

-- PDS offtake forecast: NOT RUN by default (series ends 2021-11, >4 years stale; see pipeline/07_bigquery.py PDS_MAX_STALE_MONTHS).
-- Template kept so it can be enabled if fresher data arrives. Params: ${DS} ${LAST} ${H}
SELECT lgd, 'pds_rice_wheat_t' AS series, 'timesfm2.5_univariate' AS variant, DATE '${LAST}' AS cutoff,
  DATE(forecast_timestamp) AS horizon_month, forecast_value AS forecast,
  prediction_interval_lower_bound AS p10, prediction_interval_upper_bound AS p90, ai_forecast_status AS status
FROM AI.FORECAST(
  (SELECT lgd, month, rice_t + wheat_t AS v FROM `${DS}.district_month_pds` WHERE rice_t IS NOT NULL AND wheat_t IS NOT NULL),
  data_col => 'v', timestamp_col => 'month', id_cols => ['lgd'],
  horizon => ${H}, confidence_level => 0.8, model => 'TimesFM 2.5')

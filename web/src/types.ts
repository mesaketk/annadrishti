// Types mirror docs/SCHEMA.md. Missing values are `null`, never 0.
/** Legacy keys `neutral|elnino|elnino_strong`, or `<season>:<phase>` (Addendum F), e.g. `rabi_2026_27:elnino`. */
export type ScenarioKey = string
export type PhaseId = 'lanina' | 'neutral' | 'elnino' | 'elnino_strong' | 'current'
export type SeasonStatus = 'sowing_now' | 'upcoming' | string
export interface OutlookSeason { id: string; label: string; sowing?: string; harvest?: string; status?: SeasonStatus }
/** Addendum F: kpis.outlook. Every field optional; parsed defensively. */
export interface Outlook {
  as_of?: string
  seasons?: OutlookSeason[]
  enso?: { state?: string; nino34?: number; source?: string; p_by_season?: Record<string, Partial<Record<'elnino' | 'neutral' | 'lanina', number>>> }
  default_scenario?: Record<string, string>
  refresh?: Record<string, string>
}
export type Band = 'low' | 'medium' | 'high' | 'no_data'
export type Audience = 'official' | 'farmer'
export type Lang = 'en' | 'hi' | 'mr' | 'te' | 'bn' | 'ta' | 'kn' | 'gu' | 'or'
export type Department =
  | 'collector' | 'food_civil_supplies' | 'agriculture' | 'wcd_icds' | 'rural_development' | 'health' | 'animal_husbandry'
export type Holding = 'marginal' | 'small' | 'medium_large'
export type Water = 'rainfed' | 'partial' | 'irrigated'
export interface FarmerProfile {
  holding: Holding
  water: Water
  crop: string            // one of district top crops, or 'other'
  livestock: boolean
  tenant: boolean
}

export interface CropTop { crop: string; share: number; yield_t_ha: number | null }
export interface GroupStat { area_ha: number; prod_t: number }
export interface Crops {
  year: string
  gross_cropped_area_ha: number | null
  top: CropTop[]
  groups: Record<string, GroupStat>
  foodgrain_prod_t: number | null
  simpson_div: number | null
  top_crop_share: number | null
  kharif_rabi_ratio: number | null
  yield_cv10: number | null
  irrigated_share: number | null
  rainfed_share: number | null
  small_marginal_share: number | null
  /** Addendum D (optional): per-crop cost of cultivation economics. Shape is parsed defensively (lib/extra.ts). */
  economics?: unknown
}
export interface FoodBalance {
  requirement_t: number | null
  edible_prod_t: number | null
  self_sufficiency: number | null
  pds_dependency: number | null
}
export interface Nfhs {
  year: string
  stunting: number | null
  wasting: number | null
  underweight: number | null
  child_anaemia: number | null
  women_anaemia: number | null
  women_bmi_low: number | null
}
/** Addendum D blocks. Every field optional; the UI parses these defensively (lib/extra.ts). */
export interface Markets {
  crop?: string | null
  price_elnino_spike_pct?: number | null
  price_volatility_idx?: number | null
  price_series_json?: unknown
  price_series?: unknown
}
export interface Groundwater {
  gw_premonsoon_depth_m?: number | null
  gw_decline_10y_m_per_yr?: number | null
  gw_stress_idx?: number | null
}
export interface PoshanLive {
  poshan_underweight_pct?: number | null
  poshan_stunted_pct?: number | null
  poshan_wasted_pct?: number | null
  poshan_as_of?: string | null
}
export interface Live {
  ndvi_anom: number | null
  chirps_30d_anom_pct: number | null
  wn_10d_rain_mm: number | null
  as_of: string
}
export interface Climate {
  jjas_normal_mm: number | null
  jjas_anomaly_pct: Record<string, number | null>
  elnino_mean_anomaly_pct: number | null
  neutral_mean_anomaly_pct: number | null
  lanina_mean_anomaly_pct: number | null
  tmax_anomaly_c: Record<string, number | null>
  clim_vuln_index: number | null
  live?: Live | null
}
export interface Driver { name: string; contrib: number }
export interface Actions {
  grain_preposition_t: number | null
  pulses_preposition_t: number | null
  anganwadi_children: number | null
  women_anaemia_target: number | null
  seed_bank_ha: number | null
  mgnrega_persondays: number | null
  pmfby_gap_farmers: number | null
  fodder_flag: boolean | null
  lead: Record<string, string> | null
  season?: string | null
  priority_rank_state: number | null
  priority_rank_national: number | null
}
export interface Risk {
  score: number | null
  band: Band | null
  exposure: number | null
  sensitivity: number | null
  capacity: number | null
  expected_yield_shock_pct: number | null
  drivers: Driver[]
  actions?: Actions | null
}
export interface District {
  lgd: number
  district: string
  state: string
  main_season?: 'JJAS' | 'OND' | string | null
  beta_source?: string | null
  data_quality?: { scored?: boolean; no_data_reason?: string | null } | null
  census11: string
  centroid: [number, number]
  population_2011: number | null
  population_2026: number | null
  children_u5_est: number | null
  crops: Crops | null
  food_balance: FoodBalance | null
  nutrition: { nfhs5: Nfhs | null; nfhs6: Nfhs | null; poshan_live?: PoshanLive | null } | null
  markets?: Markets | null
  groundwater?: Groundwater | null
  climate: Climate | null
  yield_sensitivity: {
    foodgrain_elnino_pct: number | null
    n_elnino_years: number | null
    by_group: Record<string, number | null>
  } | null
  risk: Record<string, Risk | null>
  hindcast: Record<string, { predicted_score: number | null; actual_foodgrain_yield_dev_pct: number | null; rain_anomaly_pct?: number | null; predicted_shock_lgbm_oos_pct?: number | null }> | null
  /** Addendum E (optional): analog / LightGBM / ensemble expected-shock block. Parsed defensively (lib/models.ts). */
  models?: unknown
  /** Addendum F (optional): rabi hindcast block, same shape as `hindcast`. */
  hindcast_rabi?: Record<string, { predicted_score: number | null; actual_foodgrain_yield_dev_pct: number | null; rain_anomaly_pct?: number | null; predicted_shock_lgbm_oos_pct?: number | null }> | null
}
export interface ActionsTotal {
  grain_preposition_t: number | null
  pulses_preposition_t: number | null
  anganwadi_children: number | null
  women_anaemia_target?: number | null
  seed_bank_ha: number | null
  mgnrega_persondays: number | null
  pmfby_gap_farmers: number | null
}
export interface ScenarioKpis {
  people_in_high_risk: number
  children_u5_in_high_risk: number
  national_expected_shock_pct: number | null
  total_deficit_t: number | null
  districts_below_self_sufficiency: number
  districts_with_balance: number
}
export interface Kpis {
  as_of: string
  enso: { state: string; nino34: number; p_historic_ond?: number; source: string }
  central_pool: { date: string; rice_lmt: number; wheat_lmt: number; total_lmt: number; norm_lmt: number; months_of_offtake: number } | null
  band_thresholds?: { low_below: number; high_from: number }
  scenario_counts?: Partial<Record<ScenarioKey, Partial<Record<Band, number>>>>
  /** Top-level values are the El Nino numbers; use by_scenario for the selected scenario. */
  people_in_high_risk?: number
  children_u5_in_high_risk?: number
  by_scenario?: Partial<Record<ScenarioKey, ScenarioKpis>>
  /** Addendum F (optional) */
  by_season_scenario?: Record<string, Partial<Record<string, Partial<ScenarioKpis>>>>
  outlook?: Outlook
  hindcast?: Record<string, { phase?: string; n?: number; spearman_rho: number | null; rho_lgbm_oos?: number | null; rho_analog_oos?: number | null; gap_lgbm_oos?: number | null }>
  /** Addendum E (optional): skill table + weights + TimesFM national summary. Parsed defensively (lib/models.ts). */
  models?: unknown
  method_note?: string
  actions_total?: Partial<Record<ScenarioKey, ActionsTotal>>
  top_states?: { state: string; grain_preposition_t: number }[]
}
export interface Timeseries {
  yield: { foodgrain_t_ha: Record<string, number | null>; by_group?: Record<string, Record<string, number | null>> }
  rain_jjas_mm: Record<string, number | null>
  oni_phase: Record<string, string>
  nfhs?: unknown[]
  pds_monthly?: { date: string; rice_t: number | null; wheat_t: number | null }[]
}
export interface ChatMsg { role: 'user' | 'assistant'; content: string; citations?: number[] }

/** One row of the pre-positioning planner (GET /api/actions). */
export interface ActionRow {
  lgd: number
  district: string
  state: string
  score: number | null
  band: Band | null
  grain_preposition_t: number | null
  pulses_preposition_t: number | null
  anganwadi_children: number | null
  women_anaemia_target: number | null
  seed_bank_ha: number | null
  mgnrega_persondays: number | null
  pmfby_gap_farmers: number | null
  fodder_flag: boolean | null
  lead_rabi: string | null
  lead_kharif: string | null
  priority_rank_state: number | null
  priority_rank_national: number | null
}

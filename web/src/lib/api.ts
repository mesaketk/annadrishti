import type {
  ActionRow, ActionsTotal, Audience, ChatMsg, Department, District, FarmerProfile, Kpis, Lang, PhaseId, ScenarioKey, Timeseries,
} from '../types'
import { scenarioLabel } from './scales'
import { globalKey, legacyKey, riskAt, scenarioKey, splitKey } from './scenario'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}

async function fetchJson<T>(url: string, init?: RequestInit, timeoutMs = 20000): Promise<T> {
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(), timeoutMs)
  try {
    const r = await fetch(url, { ...init, signal: ctl.signal })
    if (!r.ok) throw new ApiError(`${r.status} ${r.statusText}`, r.status)
    const ct = r.headers.get('content-type') ?? ''
    if (!ct.includes('json')) throw new ApiError('Not JSON (is the API running?)', 0)
    return (await r.json()) as T
  } finally {
    clearTimeout(t)
  }
}

const post = <T,>(url: string, body: unknown, timeoutMs = 90000) =>
  fetchJson<T>(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }, timeoutMs)

// ------------------------------------------------------------------ bootstrap (with mock fallback)
export interface Bootstrap { districts: District[]; kpis: Kpis; mock: boolean }

export async function bootstrap(): Promise<Bootstrap> {
  try {
    const [districts, kpis] = await Promise.all([
      fetchJson<District[]>('/api/districts', undefined, 15000),
      fetchJson<Kpis>('/api/kpis', undefined, 15000),
    ])
    if (!Array.isArray(districts) || !districts.length) throw new Error('empty')
    return { districts, kpis, mock: false }
  } catch {
    const [districts, kpis] = await Promise.all([
      fetchJson<District[]>('/mock/districts.json'),
      fetchJson<Kpis>('/mock/kpis.json'),
    ])
    return { districts, kpis, mock: true }
  }
}

export const NO_HISTORY = 'no history in demo mode'

export async function getTimeseries(lgd: number, mock: boolean): Promise<Timeseries> {
  if (!mock) return fetchJson<Timeseries>(`/api/timeseries/${lgd}`)
  // demo bundle ships only a handful of showcase districts; a 404 (or the SPA html fallback) is expected
  try {
    return await fetchJson<Timeseries>(`/mock/timeseries/${lgd}.json`)
  } catch {
    throw new ApiError(NO_HISTORY, 404)
  }
}

// ------------------------------------------------------------------ Gemini endpoints
export interface AdvisoryOpts { profile?: FarmerProfile; department?: Department }
export async function getAdvisory(d: District, audience: Audience, language: Lang, scenario: ScenarioKey, mock: boolean, opts: AdvisoryOpts = {}): Promise<string> {
  try {
    const body: Record<string, unknown> = { audience, language, scenario }
    if (audience === 'farmer' && opts.profile) body.profile = opts.profile
    if (audience === 'official' && opts.department) body.department = opts.department
    const r = await post<{ markdown: string }>(`/api/advisory/${d.lgd}`, body)
    return r.markdown
  } catch (e) {
    if (mock) { await sleep(900); return mockAdvisory(d, audience, language, scenario, opts) }
    throw e
  }
}

export async function getStateBrief(state: string, scenario: ScenarioKey, districts: District[], mock: boolean): Promise<string> {
  try {
    const r = await post<{ markdown: string }>('/api/state_brief', { state, scenario })
    return r.markdown
  } catch (e) {
    if (mock) { await sleep(1000); return mockStateBrief(state, scenario, districts) }
    throw e
  }
}

export async function getAdvisoryAudio(lgd: number, language: Lang, scenario: ScenarioKey, profile?: FarmerProfile): Promise<Blob> {
  const r = await fetch(`/api/advisory/${lgd}/audio`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ language, scenario, ...(profile ? { profile } : {}) }),
  })
  if (r.status === 503) throw new ApiError('Gemini key not configured', 503)
  if (!r.ok) throw new ApiError(`${r.status} ${r.statusText}`, r.status)
  const ct = r.headers.get('content-type') ?? ''
  if (ct.includes('text/html') || ct.includes('json')) throw new ApiError('Audio endpoint unavailable', 0)
  return r.blob()
}

export async function chat(messages: ChatMsg[], scenario: ScenarioKey, districts: District[], mock: boolean): Promise<{ reply: string; citations: number[] }> {
  try {
    const r = await post<{ reply: string; citations?: number[] }>('/api/chat', {
      messages: messages.slice(-12).map(({ role, content }) => ({ role, content: content.slice(0, 2000) })), scenario,
    })
    return { reply: r.reply, citations: r.citations ?? [] }
  } catch (e) {
    if (mock) { await sleep(900); return mockChat(messages, scenario, districts) }
    throw e
  }
}

// ------------------------------------------------------------------ planner
export interface ActionsResult { rows: ActionRow[]; totals: ActionsTotal | null }

export function normalizeRow(x: Record<string, any>): ActionRow { // eslint-disable-line @typescript-eslint/no-explicit-any
  const lead = x.lead ?? {}
  const n = (v: unknown) => (v === '' || v == null ? null : Number(v))
  return {
    lgd: Number(x.lgd), district: x.district, state: x.state,
    score: n(x.score), band: x.band ?? null,
    grain_preposition_t: n(x.grain_preposition_t), pulses_preposition_t: n(x.pulses_preposition_t),
    anganwadi_children: n(x.anganwadi_children), women_anaemia_target: n(x.women_anaemia_target),
    seed_bank_ha: n(x.seed_bank_ha), mgnrega_persondays: n(x.mgnrega_persondays), pmfby_gap_farmers: n(x.pmfby_gap_farmers),
    fodder_flag: x.fodder_flag == null || x.fodder_flag === '' ? null : x.fodder_flag === true || x.fodder_flag === 'True' || x.fodder_flag === 'true',
    lead_rabi: lead.rabi_2026_27 ?? x.lead_rabi_2026_27 ?? x.lead_rabi ?? null,
    lead_kharif: lead.kharif_2027 ?? x.lead_kharif_2027 ?? x.lead_kharif ?? null,
    priority_rank_state: n(x.priority_rank_state), priority_rank_national: n(x.priority_rank_national),
  }
}

export function deriveActionRows(districts: District[], season: string | null, phase: PhaseId): ActionRow[] {
  const rows: ActionRow[] = []
  for (const d of districts) {
    const r = d.risk[scenarioKey(d, season, phase)]
    if (!r?.actions) continue
    rows.push(normalizeRow({ ...r.actions, lgd: d.lgd, district: d.district, state: d.state, score: r.score, band: r.band }))
  }
  return rows.sort((a, b) => (a.priority_rank_national ?? 1e9) - (b.priority_rank_national ?? 1e9))
}

async function fetchActions(scenario: ScenarioKey, kpis: Kpis): Promise<ActionsResult> {
  const r = await fetchJson<unknown>(`/api/actions?scenario=${encodeURIComponent(scenario)}`)
  const arr = Array.isArray(r) ? r : ((r as { rows?: unknown[]; actions?: unknown[] }).rows ?? (r as { actions?: unknown[] }).actions ?? [])
  const totals = (!Array.isArray(r) && ((r as { actions_total?: ActionsTotal }).actions_total ?? (r as { kpis?: { actions_total?: Record<string, ActionsTotal> } }).kpis?.actions_total?.[scenario])) || kpis.actions_total?.[scenario] || null
  const rows = (arr as Record<string, unknown>[]).map(normalizeRow).map((r, i) => (r.priority_rank_national == null ? { ...r, priority_rank_national: i + 1 } : r))
  return { rows, totals }
}

/**
 * Order: API with the effective (season-qualified) key -> rows derived from the loaded districts
 * -> API with the legacy key (older servers that only know neutral|elnino|elnino_strong).
 */
export async function getActions(season: string | null, phase: PhaseId, districts: District[], kpis: Kpis, mock: boolean): Promise<ActionsResult> {
  const key = globalKey(districts, season, phase)
  const legacy = legacyKey(phase)
  if (!mock) {
    try {
      const r = await fetchActions(key, kpis)
      if (r.rows.length) return r
    } catch { /* 422 / network: fall through */ }
  }
  const derived = deriveActionRows(districts, season, phase)
  const totals = kpis.actions_total?.[key] ?? kpis.actions_total?.[legacy] ?? null
  if (derived.length || mock || key === legacy) return { rows: derived, totals }
  try { return await fetchActions(legacy, kpis) } catch { return { rows: derived, totals } }
}

export function actionsCsvUrl(scenario: ScenarioKey, state: string, band: string) {
  const q = new URLSearchParams({ scenario, format: 'csv' })
  if (state) q.set('state', state)
  if (band) q.set('band', band)
  return `/api/actions?${q}`
}

/** Client-side CSV (used when the API is unavailable / mock mode). */
export function rowsToCsv(rows: ActionRow[]): string {
  const cols: (keyof ActionRow)[] = ['priority_rank_national', 'state', 'district', 'lgd', 'score', 'band', 'grain_preposition_t', 'pulses_preposition_t', 'anganwadi_children', 'women_anaemia_target', 'seed_bank_ha', 'mgnrega_persondays', 'pmfby_gap_farmers', 'fodder_flag', 'lead_rabi', 'lead_kharif']
  const esc = (v: unknown) => (v == null ? '' : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v))
  return [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n')
}

// ------------------------------------------------------------------ mock LLM text (demo only)
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
const fmt = (n: number | null | undefined) => (n == null ? 'n/a' : Math.round(n).toLocaleString('en-IN'))

function mockAdvisory(d: District, audience: Audience, lang: Lang, sc: ScenarioKey, opts: AdvisoryOpts = {}): string {
  const r = riskAt(d, sc)
  const top = d.crops?.top.slice(0, 2).map((c) => c.crop).join(' and ') ?? 'local crops'
  if (audience === 'official') {
    return `> **Demo text** (API offline) - real briefings are generated by Gemini from the district evidence.\n\n## ${d.district}, ${d.state} - ${scenarioLabel(sc)}${opts.department ? ` - ${opts.department.replace(/_/g, ' ')} lens` : ''}\n\n**Why it is ${r?.band ?? 'n/a'}:** risk score **${r?.score ?? 'n/a'}/100**; ${(r?.drivers ?? []).slice(0, 3).map((x) => x.name.replace(/_/g, ' ')).join(', ')} dominate.\n\n**Expected impact:** foodgrain yield ${r?.expected_yield_shock_pct ?? 'n/a'}% vs trend; self-sufficiency ${d.food_balance?.self_sufficiency ?? 'n/a'}x.\n\n**Recommended actions**\n- Pre-position ${fmt(r?.actions?.grain_preposition_t)} t foodgrain and ${fmt(r?.actions?.pulses_preposition_t)} t pulses before 15 Nov\n- Top up Anganwadi supplementary nutrition for ~${fmt(r?.actions?.anganwadi_children)} children\n- Stock short-duration / millet seed for rabi\n- Pre-approve MGNREGA works for the lean period`
  }
  const T: Partial<Record<Lang, string>> = {
    en: `**Demo text.** Farmers in ${d.district}: this year's rains may be weaker (El Niño). Consider short-duration varieties of ${top}, sow on the first good rain, and keep a small area for pulses/millets. Check PMFBY enrolment before the cut-off date.`,
    hi: `**डेमो पाठ।** ${d.district} के किसान भाइयों: इस साल एल नीनो के कारण बारिश कम हो सकती है। ${top} की कम अवधि वाली किस्में चुनें, पहली अच्छी बारिश पर बुवाई करें और दलहन/मोटे अनाज के लिए थोड़ा खेत रखें। फसल बीमा (PMFBY) की अंतिम तिथि से पहले नामांकन कराएँ।`,
    mr: `**डेमो मजकूर.** ${d.district} मधील शेतकरी बांधवांनो: यंदा एल निनोमुळे पाऊस कमी राहू शकतो. ${top} च्या कमी कालावधीच्या जाती निवडा, पहिल्या चांगल्या पावसावर पेरणी करा आणि कडधान्य/भरड धान्यासाठी थोडी जमीन ठेवा. पीक विमा (PMFBY) नोंदणी वेळेत करा.`,
    te: `**డెమో పాఠ్యం.** ${d.district} రైతు సోదరులారా: ఈ ఏడాది ఎల్ నినో వల్ల వర్షాలు తక్కువగా ఉండవచ్చు. ${top} లో తక్కువ కాలపు రకాలను ఎంచుకోండి, మొదటి మంచి వర్షానికి విత్తండి, పప్పుధాన్యాలు/చిరుధాన్యాల కోసం కొంత భూమి ఉంచండి. పంటల బీమా (PMFBY) గడువు లోపు నమోదు చేసుకోండి.`,
  }
  const p = opts.profile
  const pre = p ? `*Profile: ${p.holding} · ${p.water} · ${p.crop}${p.livestock ? ' · livestock' : ''}${p.tenant ? ' · tenant' : ''}*\n\n` : ''
  return pre + (T[lang] ?? `${T.en}\n\n*(Demo text is only available in English, Hindi, Marathi and Telugu; language: ${lang})*`)
}

function mockStateBrief(state: string, sc: ScenarioKey, districts: District[]): string {
  const rows = deriveActionRows(districts.filter((d) => d.state === state), ...splitKey(sc)).slice(0, 5)
  const tot = rows.reduce((a, r) => a + (r.grain_preposition_t ?? 0), 0)
  return `> **Demo text** (API offline).\n\n# ${state}: pre-positioning plan (${scenarioLabel(sc)})\n\n**Top districts:** ${rows.map((r) => `${r.district} (${r.score})`).join(', ') || 'none'}.\n\n**Quantities (top 5):** ~${fmt(tot)} t extra foodgrain through PDS/OMSS.\n\n## Timeline\n- By 15 Nov 2026: rabi seed + foodgrain movement\n- By 15 May 2027: kharif contingency seed\n\n## Who does what\n- **Food & Civil Supplies:** stock movement\n- **WCD/ICDS:** nutrition top-up\n- **Agriculture:** seed bank, PMFBY drive\n- **Rural Development:** MGNREGA shelf of works\n- **Health:** anaemia / SAM screening`
}

function mockChat(msgs: ChatMsg[], sc: ScenarioKey, districts: District[]): { reply: string; citations: number[] } {
  const q = msgs[msgs.length - 1].content.toLowerCase()
  const st = [...new Set(districts.map((d) => d.state))].find((s) => q.includes(s.toLowerCase()))
  const pool = districts.filter((d) => !st || d.state === st).sort((a, b) => (riskAt(b, sc)?.score ?? 0) - (riskAt(a, sc)?.score ?? 0)).slice(0, 5)
  return {
    reply: `*Demo reply (API offline).* Highest-risk districts${st ? ` in **${st}**` : ''} under **${scenarioLabel(sc)}**:\n\n${pool.map((d, i) => `${i + 1}. **${d.district}** (${d.state}) - score ${riskAt(d, sc)?.score}, yield shock ${riskAt(d, sc)?.expected_yield_shock_pct}%`).join('\n')}`,
    citations: pool.map((d) => d.lgd),
  }
}

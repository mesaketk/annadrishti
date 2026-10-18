// Plain-language helpers shared by the shell (and usable by the drawer): band words, tones, one-sentence summaries.
import type { Band, Department, District, Kpis, Lang, PhaseId } from '../types'
import { riskAt, seasonsOf, splitKey } from './scenario'
import { M3 } from './m3'

export type Tone = 'low' | 'watch' | 'act' | 'info' | 'accent' | 'muted' | 'nodata'

/** Risk band -> semantic tone (high = act, medium = watch, low = low). */
export const bandTone = (b: Band | null | undefined): Tone => (b === 'high' ? 'act' : b === 'medium' ? 'watch' : b === 'low' ? 'low' : 'nodata')
export const bandWord = (b: Band | null | undefined): string => (b === 'high' ? 'Act now' : b === 'medium' ? 'Watch' : b === 'low' ? 'Low risk' : 'No estimate')
export const TONE_HEX: Record<Tone, string> = { low: M3.lowFill, watch: M3.watchFill, act: M3.actFill, info: M3.tertiary, accent: M3.primary, muted: M3.onSurfaceVariant, nodata: M3.outlineVariant }

export const PHASE_PLAIN: Record<PhaseId, string> = {
  current: 'Most likely outlook', neutral: 'Normal year', elnino: 'El Niño year', elnino_strong: 'Strong El Niño', lanina: 'La Niña year',
}
const PHASE_IF: Record<PhaseId, string> = {
  current: 'on the current outlook', neutral: 'in a normal year', elnino: 'if El Niño persists', elnino_strong: 'if El Niño is strong', lanina: 'if La Niña develops',
}

const DRIVER_PLAIN: Record<string, string> = {
  rainfed_share: 'rainfed crops', elnino_rain_deficit: 'weaker rain in El Niño years', yield_cv: 'unstable harvests',
  child_stunting: 'child nutrition', small_marginal_share: 'many small farms', low_irrigation: 'little irrigation',
  pds_dependency: 'reliance on ration supply', food_deficit: 'a local food shortfall', crop_concentration: 'dependence on few crops',
  clim_vuln_index: 'climate vulnerability', price_spike_risk: 'food price swings', groundwater_stress: 'falling groundwater',
}
export const driverPlain = (n: string) => DRIVER_PLAIN[n] ?? n.replace(/_/g, ' ')

/** `imputed` flag on the risk block, or any imputed value recorded for the district (Addendum G). */
export function isImputed(d: District, key: string): boolean {
  const r = riskAt(d, key) as (Record<string, unknown> | null)
  if (r?.imputed === true) return true
  const dq = d.data_quality as { imputed_count?: number } | null | undefined
  return (dq?.imputed_count ?? 0) > 0
}

export function seasonLabel(k: Kpis | null | undefined, season: string | null): string {
  return seasonsOf(k).find((s) => s.id === season)?.label ?? 'this season'
}

/** Level-0 sentence: "Nandurbar: high risk in Rabi 2026-27 if El Niño persists, mainly rainfed crops and child nutrition." */
export function districtSentence(d: District, key: string, kpis: Kpis | null | undefined): string {
  const r = riskAt(d, key)
  const [season, phase] = splitKey(key)
  if (!r || r.band == null || r.band === 'no_data' || r.score == null) return `${d.district}: no estimate available for this district yet.`
  const lvl = r.band === 'high' ? 'high risk' : r.band === 'medium' ? 'watch closely' : 'lower risk'
  const top = (r.drivers ?? []).slice(0, 2).map((x) => driverPlain(x.name))
  const why = r.band === 'low' || !top.length ? '' : `, mainly ${top.join(' and ')}`
  const imp = isImputed(d, key) ? ' (partly estimated from nearby districts)' : ''
  return `${d.district}: ${lvl} in ${seasonLabel(kpis, season)} ${PHASE_IF[phase]}${why}${imp}.`
}

/** 244720510 -> "24.5 crore"; 1999417 -> "20 lakh". Max 1 decimal, unit spelled. */
export function plainCount(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '–'
  const a = Math.abs(n)
  const r = (v: number) => (v >= 100 ? Math.round(v).toString() : (Math.round(v * 10) / 10).toString())
  if (a >= 1e7) return `${r(n / 1e7)} crore`
  if (a >= 1e5) return `${r(n / 1e5)} lakh`
  if (a >= 1e3) return `${Math.round(n / 1e3)} thousand`
  return String(Math.round(n))
}

export const LANGS: { id: Lang; native: string; english: string }[] = [
  { id: 'en', native: 'English', english: 'English' },
  { id: 'hi', native: 'हिन्दी', english: 'Hindi' },
  { id: 'mr', native: 'मराठी', english: 'Marathi' },
  { id: 'te', native: 'తెలుగు', english: 'Telugu' },
  { id: 'bn', native: 'বাংলা', english: 'Bengali' },
  { id: 'ta', native: 'தமிழ்', english: 'Tamil' },
  { id: 'kn', native: 'ಕನ್ನಡ', english: 'Kannada' },
  { id: 'gu', native: 'ગુજરાતી', english: 'Gujarati' },
  { id: 'or', native: 'ଓଡ଼ିଆ', english: 'Odia' },
]
export const isLang = (x: unknown): x is Lang => LANGS.some((l) => l.id === x)

export const DEPARTMENTS: { id: Department; label: string; short: string }[] = [
  { id: 'collector', label: 'District Collector (whole district)', short: 'Collector' },
  { id: 'food_civil_supplies', label: 'Food & Civil Supplies (ration shops)', short: 'Food & Civil Supplies' },
  { id: 'agriculture', label: 'Agriculture (seed, crop insurance)', short: 'Agriculture' },
  { id: 'wcd_icds', label: 'Women & Child Development (Anganwadi)', short: 'Women & Child Dev.' },
  { id: 'rural_development', label: 'Rural Development (NREGA works)', short: 'Rural Development' },
  { id: 'health', label: 'Health', short: 'Health' },
  { id: 'animal_husbandry', label: 'Animal Husbandry (fodder)', short: 'Animal Husbandry' },
]
export const isDept = (x: unknown): x is Department => DEPARTMENTS.some((d) => d.id === x)

/** Small string table for the shell's own farmer-facing copy (en + 8 languages). */
type Str = 'pick' | 'locate' | 'change' | 'search' | 'home' | 'ask' | 'language' | 'located' | 'locfail'
const T: Record<Lang, Record<Str, string>> = {
  en: { pick: 'Choose your district', locate: 'Use my location', change: 'Change', search: 'Type district or state', home: 'My district', ask: 'Ask', language: 'Language', located: 'Nearest district found', locfail: 'Could not get your location. Please search instead.' },
  hi: { pick: 'अपना ज़िला चुनें', locate: 'मेरी लोकेशन का उपयोग करें', change: 'बदलें', search: 'ज़िला या राज्य लिखें', home: 'मेरा ज़िला', ask: 'पूछें', language: 'भाषा', located: 'सबसे नज़दीकी ज़िला मिल गया', locfail: 'लोकेशन नहीं मिली। कृपया ज़िला खोजें।' },
  mr: { pick: 'तुमचा जिल्हा निवडा', locate: 'माझे स्थान वापरा', change: 'बदला', search: 'जिल्हा किंवा राज्य लिहा', home: 'माझा जिल्हा', ask: 'विचारा', language: 'भाषा', located: 'जवळचा जिल्हा सापडला', locfail: 'स्थान मिळाले नाही. कृपया जिल्हा शोधा.' },
  te: { pick: 'మీ జిల్లాను ఎంచుకోండి', locate: 'నా స్థానాన్ని ఉపయోగించండి', change: 'మార్చండి', search: 'జిల్లా లేదా రాష్ట్రం టైప్ చేయండి', home: 'నా జిల్లా', ask: 'అడగండి', language: 'భాష', located: 'దగ్గరి జిల్లా దొరికింది', locfail: 'స్థానం దొరకలేదు. దయచేసి జిల్లాను వెతకండి.' },
  bn: { pick: 'আপনার জেলা বেছে নিন', locate: 'আমার অবস্থান ব্যবহার করুন', change: 'বদলান', search: 'জেলা বা রাজ্য লিখুন', home: 'আমার জেলা', ask: 'জিজ্ঞাসা', language: 'ভাষা', located: 'কাছের জেলা পাওয়া গেছে', locfail: 'অবস্থান পাওয়া যায়নি। অনুগ্রহ করে জেলা খুঁজুন।' },
  ta: { pick: 'உங்கள் மாவட்டத்தைத் தேர்ந்தெடுக்கவும்', locate: 'என் இருப்பிடத்தைப் பயன்படுத்து', change: 'மாற்று', search: 'மாவட்டம் அல்லது மாநிலம் தட்டச்சு செய்க', home: 'என் மாவட்டம்', ask: 'கேள்', language: 'மொழி', located: 'அருகிலுள்ள மாவட்டம் கிடைத்தது', locfail: 'இருப்பிடம் கிடைக்கவில்லை. மாவட்டத்தைத் தேடுங்கள்.' },
  kn: { pick: 'ನಿಮ್ಮ ಜಿಲ್ಲೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ', locate: 'ನನ್ನ ಸ್ಥಳ ಬಳಸಿ', change: 'ಬದಲಿಸಿ', search: 'ಜಿಲ್ಲೆ ಅಥವಾ ರಾಜ್ಯ ಟೈಪ್ ಮಾಡಿ', home: 'ನನ್ನ ಜಿಲ್ಲೆ', ask: 'ಕೇಳಿ', language: 'ಭಾಷೆ', located: 'ಹತ್ತಿರದ ಜಿಲ್ಲೆ ಸಿಕ್ಕಿದೆ', locfail: 'ಸ್ಥಳ ಸಿಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಜಿಲ್ಲೆಯನ್ನು ಹುಡುಕಿ.' },
  gu: { pick: 'તમારો જિલ્લો પસંદ કરો', locate: 'મારું સ્થાન વાપરો', change: 'બદલો', search: 'જિલ્લો અથવા રાજ્ય લખો', home: 'મારો જિલ્લો', ask: 'પૂછો', language: 'ભાષા', located: 'નજીકનો જિલ્લો મળ્યો', locfail: 'સ્થાન મળ્યું નથી. કૃપા કરીને જિલ્લો શોધો.' },
  or: { pick: 'ଆପଣଙ୍କ ଜିଲ୍ଲା ବାଛନ୍ତୁ', locate: 'ମୋ ସ୍ଥାନ ବ୍ୟବହାର କରନ୍ତୁ', change: 'ବଦଳାନ୍ତୁ', search: 'ଜିଲ୍ଲା କିମ୍ବା ରାଜ୍ୟ ଲେଖନ୍ତୁ', home: 'ମୋ ଜିଲ୍ଲା', ask: 'ପଚାରନ୍ତୁ', language: 'ଭାଷା', located: 'ପାଖ ଜିଲ୍ଲା ମିଳିଲା', locfail: 'ସ୍ଥାନ ମିଳିଲା ନାହିଁ। ଦୟାକରି ଜିଲ୍ଲା ଖୋଜନ୍ତୁ।' },
}
export const tr = (lang: Lang, k: Str) => T[lang]?.[k] ?? T.en[k]

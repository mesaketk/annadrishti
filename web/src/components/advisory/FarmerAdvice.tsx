import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, getAdvisory, getAdvisoryAudio } from '../../lib/api'
import { defaultProfile, profileKey } from '../../lib/extra'
import { useStore } from '../../lib/store'
import { useScenario } from '../../lib/useScenario'
import type { District, FarmerProfile, Holding, Lang, Water } from '../../types'
import { t } from '../drawer/i18n'
import { cropsForSeason } from '../drawer/outlook'
import { Button, ErrorNote, GeminiButton, GeminiCaption, Skeleton, cx } from '../drawer/ui'
import { Chip, Icon } from '../ui'
import { BTN_BASE, BTN_S, BTN_V, CARD } from '../ui/m3'
import { splitEconomics } from './economics'
import Markdown from './Markdown'

const cache = new Map<string, string>()
const audioCache = new Map<string, string>() // key -> object URL

const HOLDINGS: Holding[] = ['marginal', 'small', 'medium_large']
const WATERS: Water[] = ['rainfed', 'partial', 'irrigated']
export const LANG_CHIPS: { id: Lang; label: string }[] = [
  { id: 'en', label: 'English' }, { id: 'hi', label: 'हिन्दी' }, { id: 'mr', label: 'मराठी' }, { id: 'te', label: 'తెలుగు' },
  { id: 'bn', label: 'বাংলা' }, { id: 'ta', label: 'தமிழ்' }, { id: 'kn', label: 'ಕನ್ನಡ' }, { id: 'gu', label: 'ગુજરાતી' }, { id: 'or', label: 'ଓଡ଼ିଆ' },
]

function Chips<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { id: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <fieldset className="min-w-0">
      <legend className="mb-3 md-title-medium text-on-surface">{label}</legend>
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <Chip key={o.id} size="lg" role="radio" aria-checked={o.id === value} selected={o.id === value} onClick={() => onChange(o.id)}>{o.label}</Chip>
        ))}
      </div>
    </fieldset>
  )
}
function YesNo({ label, value, lang, onChange }: { label: string; value: boolean; lang: Lang; onChange: (v: boolean) => void }) {
  return <Chips label={label} value={value ? 'y' : 'n'} onChange={(v) => onChange(v === 'y')} options={[{ id: 'n', label: t(lang, 'no') }, { id: 'y', label: t(lang, 'yes') }]} />
}

export default function FarmerAdvice({ d, scenarioKey, lang, onLanguageChange }: { d: District; scenarioKey: string; lang: Lang; onLanguageChange: (l: Lang) => void }) {
  const mock = useStore((s) => s.mock)
  const [profile, setProfile] = useState<FarmerProfile>(() => defaultProfile(d))
  const [, bump] = useState(0)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const key = `${d.lgd}|${scenarioKey}|${lang}|${profileKey(profile)}`
  const md = cache.get(key) ?? null
  const { season } = useScenario()
  const crops = useMemo(() => [...new Set(cropsForSeason(d, season).map((c) => c.crop))], [d, season])
  // keep the selected crop valid when the season (and so the crop list) changes
  useEffect(() => {
    setProfile((p) => (p.crop === 'other' || crops.includes(p.crop) || !crops.length ? p : { ...p, crop: crops[0] }))
  }, [crops])
  const set = <K extends keyof FarmerProfile>(k: K, v: FarmerProfile[K]) => { setProfile((p) => ({ ...p, [k]: v })); setErr(null) }

  const run = useCallback(async (force = false) => {
    if (force) cache.delete(key)
    if (cache.has(key)) { bump((n) => n + 1); return }
    setBusy(true); setErr(null)
    try { cache.set(key, await getAdvisory(d, 'farmer', lang, scenarioKey, mock, { profile })) }
    catch { setErr(t(lang, 'err.generic')) }
    finally { setBusy(false); bump((n) => n + 1) }
  }, [key, d, lang, scenarioKey, mock, profile])

  const adv = useMemo(() => (md ? splitEconomics(md) : null), [md])
  const plain = adv ? adv.body.replace(/[*_#>`]/g, '').trim() : ''
  const shareText = `AnnaDrishti · ${d.district}\n\n${plain}`
  const copy = async () => { try { await navigator.clipboard.writeText(shareText); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { /* blocked */ } }

  return (
    <div className="space-y-4">
      <div className="hide-scrollbar -mx-4 flex items-center gap-2 overflow-x-auto px-4 py-2" role="group" aria-label={t(lang, 'lang.label')}>
        {LANG_CHIPS.map((l) => (
          <Chip key={l.id} size="lg" onClick={() => onLanguageChange(l.id)} aria-pressed={l.id === lang} selected={l.id === lang} lang={l.id}>{l.label}</Chip>
        ))}
      </div>

      <section aria-label={t(lang, 'form.title')} className={cx(CARD, 'space-y-6 !rounded-m3-lg p-4')} lang={lang}>
        <h3 className="md-title-large text-on-surface">{t(lang, 'form.title')}</h3>
        <Chips label={t(lang, 'form.holding')} value={profile.holding} onChange={(v) => set('holding', v)} options={HOLDINGS.map((h) => ({ id: h, label: t(lang, `holding.${h}`) }))} />
        <Chips label={t(lang, 'form.water')} value={profile.water} onChange={(v) => set('water', v)} options={WATERS.map((w) => ({ id: w, label: t(lang, `water.${w}`) }))} />
        <Chips label={t(lang, 'form.crop')} value={profile.crop} onChange={(v) => set('crop', v)} options={[...crops.map((c) => ({ id: c, label: c })), { id: 'other', label: t(lang, 'crop.other') }]} />
        <YesNo label={t(lang, 'form.livestock')} value={profile.livestock} lang={lang} onChange={(v) => set('livestock', v)} />
        <YesNo label={t(lang, 'form.tenant')} value={profile.tenant} lang={lang} onChange={(v) => set('tenant', v)} />
        <div className="space-y-2">
          <GeminiButton size="lg" className="w-full" disabled={busy} onClick={() => void run(!!md)} aria-busy={busy}>
            {busy ? t(lang, 'btn.getting') : md ? t(lang, 'btn.again') : t(lang, 'btn.get')}
          </GeminiButton>
          <div className="text-center"><GeminiCaption text={t(lang, 'brand.gemini')} /></div>
        </div>
        {err && <ErrorNote onRetry={() => void run(true)}>{err}</ErrorNote>}
      </section>

      {busy && <div className={cx(CARD, 'space-y-2 !rounded-m3-lg p-4')} aria-live="polite"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-11/12" /><Skeleton className="h-4 w-4/5" /></div>}

      {adv && !busy && (
        <article className="rounded-m3-lg border border-primary/50 bg-surface-container-low p-4" lang={lang} aria-label={`Spark · ${t(lang, 'advice.for')}`}>
          <h3 className="mb-2 md-title-large text-on-primary-container">Spark · {t(lang, 'advice.for')}</h3>
          <Markdown large lang={lang}>{adv.body}</Markdown>
          {adv.econ && <p className="mt-3 md-body-small text-muted" data-testid="advice-econ">{t(lang, 'econ.label')}: {adv.econ}</p>}
          <div className="mt-4 flex flex-wrap gap-2 border-t border-outline-variant pt-4">
            <ListenButton d={d} lang={lang} scenarioKey={scenarioKey} profile={profile} />
            <a href={`https://wa.me/?text=${encodeURIComponent(shareText)}`} target="_blank" rel="noopener noreferrer"
              className={cx(BTN_BASE, BTN_V.secondary, BTN_S.md)}>
              <Icon name="share" size={20} />{t(lang, 'btn.share')}
            </a>
            <Button variant="outlined" onClick={copy} iconLeft={<Icon name={copied ? 'check' : 'content_copy'} size={20} />}>{copied ? t(lang, 'btn.copied') : t(lang, 'btn.copy')}</Button>
          </div>
          <AudioPlayer d={d} lang={lang} scenarioKey={scenarioKey} profile={profile} />
          <div className="mt-3"><GeminiCaption text={t(lang, 'brand.gemini')} /></div>
        </article>
      )}
    </div>
  )
}

// ---- audio (shared state between the button and the player via cache + custom event)
const audioKey = (d: District, lang: Lang, sc: string, p: FarmerProfile) => `${d.lgd}|${lang}|${sc}|${profileKey(p)}`
function useAudio(d: District, lang: Lang, sc: string, p: FarmerProfile) {
  const key = audioKey(d, lang, sc, p)
  const [url, setUrl] = useState<string | null>(audioCache.get(key) ?? null)
  useEffect(() => { setUrl(audioCache.get(key) ?? null) }, [key])
  useEffect(() => {
    const h = (e: Event) => { if ((e as CustomEvent<string>).detail === key) setUrl(audioCache.get(key) ?? null) }
    window.addEventListener('annadrishti-audio', h)
    return () => window.removeEventListener('annadrishti-audio', h)
  }, [key])
  return { key, url }
}
function ListenButton({ d, lang, scenarioKey, profile }: { d: District; lang: Lang; scenarioKey: string; profile: FarmerProfile }) {
  const { key } = useAudio(d, lang, scenarioKey, profile)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const go = async () => {
    setErr(null)
    if (audioCache.has(key)) { window.dispatchEvent(new CustomEvent('annadrishti-audio', { detail: key })); return }
    setLoading(true)
    try {
      const blob = await getAdvisoryAudio(d.lgd, lang, scenarioKey, profile)
      audioCache.set(key, URL.createObjectURL(blob))
      window.dispatchEvent(new CustomEvent('annadrishti-audio', { detail: key }))
    } catch (e) {
      setErr(e instanceof ApiError && e.status === 503 ? t(lang, 'err.audio') : t(lang, 'err.audio'))
    } finally { setLoading(false) }
  }
  return (
    <>
      <GeminiButton onClick={() => void go()} disabled={loading} aria-label={t(lang, 'btn.listen')}>
        {loading ? t(lang, 'btn.loading') : t(lang, 'btn.listen')}
      </GeminiButton>
      {err && <span role="alert" className="basis-full md-body-medium text-act-ink">{err}</span>}
    </>
  )
}
function AudioPlayer({ d, lang, scenarioKey, profile }: { d: District; lang: Lang; scenarioKey: string; profile: FarmerProfile }) {
  const { url } = useAudio(d, lang, scenarioKey, profile)
  if (!url) return null
  return <audio key={url} src={url} controls autoPlay className="mt-3 h-12 w-full" />
}

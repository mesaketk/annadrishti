// Generates the Material 3 (Material You) colour tokens for AnnaDrishti.
//   node scripts/m3_theme.mjs        ->  src/m3.css  (CSS variables, light + [data-theme=dark])
//                                        src/lib/m3.ts (light hex mirror for maplibre / Recharts, which cannot read CSS vars)
// Algorithm: @material/material-color-utilities (HCT, tonal spot scheme) from the seed below.
// Semantic risk colours are fixed colour-blind-safe custom colours: low = blue, watch = amber, act = vermilion (M3 error stays red for real errors).
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { register } from 'node:module'

// material-color-utilities 0.4 ships ESM with extensionless relative imports, which plain Node cannot resolve:
// add a tiny resolve hook that retries with ".js" (the bundler-style resolution Vite uses).
register('data:text/javascript,' + encodeURIComponent(`
export async function resolve(spec, ctx, next) {
  try { return await next(spec, ctx) }
  catch (e) { if (e.code === 'ERR_MODULE_NOT_FOUND' && spec.startsWith('.') && !/\\.[cm]?js$/.test(spec)) return next(spec + '.js', ctx); throw e }
}`), import.meta.url)
const { Hct, SchemeTonalSpot, MaterialDynamicColors: M, TonalPalette, Blend, argbFromHex, hexFromArgb, customColor } =
  await import('@material/material-color-utilities')

const SEED = '#3E7C3A'
const here = dirname(fileURLToPath(import.meta.url))
const seed = argbFromHex(SEED)

// ---------------------------------------------------------------- roles
const ROLES = {
  primary: M.primary, 'on-primary': M.onPrimary, 'primary-container': M.primaryContainer, 'on-primary-container': M.onPrimaryContainer,
  secondary: M.secondary, 'on-secondary': M.onSecondary, 'secondary-container': M.secondaryContainer, 'on-secondary-container': M.onSecondaryContainer,
  tertiary: M.tertiary, 'on-tertiary': M.onTertiary, 'tertiary-container': M.tertiaryContainer, 'on-tertiary-container': M.onTertiaryContainer,
  error: M.error, 'on-error': M.onError, 'error-container': M.errorContainer, 'on-error-container': M.onErrorContainer,
  background: M.background, 'on-background': M.onBackground,
  surface: M.surface, 'surface-dim': M.surfaceDim, 'surface-bright': M.surfaceBright,
  'surface-container-lowest': M.surfaceContainerLowest, 'surface-container-low': M.surfaceContainerLow, 'surface-container': M.surfaceContainer,
  'surface-container-high': M.surfaceContainerHigh, 'surface-container-highest': M.surfaceContainerHighest,
  'on-surface': M.onSurface, 'surface-variant': M.surfaceVariant, 'on-surface-variant': M.onSurfaceVariant,
  outline: M.outline, 'outline-variant': M.outlineVariant,
  'inverse-surface': M.inverseSurface, 'inverse-on-surface': M.inverseOnSurface, 'inverse-primary': M.inversePrimary,
  'surface-tint': M.surfaceTint, shadow: M.shadow, scrim: M.scrim,
}

// Colour-blind-safe semantic risk colours (Okabe-Ito style, blue -> amber -> vermilion). Hexes are exact (not harmonised to the seed):
// fill = map / lamp / chart mark, container = chip background. Text tones (derived from the same hue) are WCAG-checked below.
const CUSTOM = [
  { name: 'low', fill: '#2F6DB5', container: '#DCE8F7' }, // blue: low risk
  { name: 'watch', fill: '#E8A317', container: '#FBECC8' }, // amber: watch
  { name: 'act', fill: '#D55E00', container: '#F9DCCB' }, // vermilion: act now
]

function buildScheme(dark) {
  const s = new SchemeTonalSpot(Hct.fromInt(seed), dark, 0)
  const out = {}
  for (const [k, c] of Object.entries(ROLES)) out[k] = c.getArgb(s)
  for (const cc of CUSTOM) {
    const f = Hct.fromInt(argbFromHex(cc.fill))
    const pal = TonalPalette.fromHueAndChroma(f.hue, Math.max(f.chroma, 36))
    if (dark) {
      out[cc.name] = pal.tone(80); out[`on-${cc.name}`] = pal.tone(20)
      out[`${cc.name}-container`] = pal.tone(30); out[`on-${cc.name}-container`] = pal.tone(90)
      out[`${cc.name}-fill`] = f.tone >= 55 ? argbFromHex(cc.fill) : pal.tone(60)
    } else {
      out[cc.name] = pal.tone(cc.name === 'watch' ? 38 : 40); out[`on-${cc.name}`] = 0xffffffff
      out[`${cc.name}-container`] = argbFromHex(cc.container); out[`on-${cc.name}-container`] = pal.tone(cc.name === 'watch' ? 15 : 12)
      out[`${cc.name}-fill`] = argbFromHex(cc.fill)
    }
  }
  // light orange used for El Nino shading on charts (= act container)
  out['elnino-shade'] = out['act-container']
  out.nodata = out['outline-variant']
  return out
}
const light = buildScheme(false)
const dark = buildScheme(true)

// ---------------------------------------------------------------- WCAG check
const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }
const lum = (argb) => 0.2126 * lin((argb >> 16) & 255) + 0.7152 * lin((argb >> 8) & 255) + 0.0722 * lin(argb & 255)
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }
const PAIRS = [
  ['on-surface', 'surface'], ['on-surface-variant', 'surface'], ['on-surface-variant', 'surface-container'], ['on-surface-variant', 'surface-container-highest'],
  ['on-primary', 'primary'], ['on-primary-container', 'primary-container'], ['on-secondary-container', 'secondary-container'], ['on-tertiary-container', 'tertiary-container'],
  ['on-low-container', 'low-container'], ['on-watch-container', 'watch-container'], ['on-act-container', 'act-container'], ['on-error-container', 'error-container'],
  ['on-low', 'low'], ['on-watch', 'watch'], ['on-act', 'act'], ['on-error', 'error'],
  ['on-low-container', 'surface-container-low'], ['on-watch-container', 'surface-container-low'], ['on-act-container', 'surface-container-low'],
  ['low', 'surface'], ['watch', 'surface'], ['act', 'surface'],
  ['inverse-on-surface', 'inverse-surface'], ['primary', 'surface'], ['secondary', 'surface'],
]
let bad = 0
for (const [name, sch] of [['light', light], ['dark', dark]]) {
  for (const [fg, bg] of PAIRS) {
    const r = ratio(sch[fg], sch[bg])
    if (r < 4.5) { bad++; console.error(`WCAG FAIL (${name}) ${fg} on ${bg}: ${r.toFixed(2)}`) }
  }
}
console.log(`WCAG AA text pairs checked: ${PAIRS.length * 2}, failures: ${bad}`)
// non-text marks against the card surface should reach 3:1
for (const k of ['low-fill', 'watch-fill', 'act-fill', 'elnino-shade']) console.log(`  ${k} ${hexFromArgb(light[k])} vs surface-container-low ${ratio(light[k], light['surface-container-low']).toFixed(2)}:1`)
if (bad) process.exit(1)

// ---------------------------------------------------------------- emit
const rgb = (a) => `${(a >> 16) & 255} ${(a >> 8) & 255} ${a & 255}`
// custom colours (low / watch / act / nodata and their fills) live in the M3 extended namespace
const EXT = /^(on-)?(low|watch|act|nodata)(-|$)|-fill$|^elnino-shade$/
const block = (sch) => Object.entries(sch).map(([k, v]) => `  --md-${EXT.test(k) ? 'ext' : 'sys'}-color-${k}: ${hexFromArgb(v)};\n  --md-rgb-${k}: ${rgb(v)};`).join('\n')
const css = `/* GENERATED by scripts/m3_theme.mjs from seed ${SEED}. Do not edit by hand. */
/* Material 3 colour roles (--md-sys-color-*), plus --md-rgb-* channel triplets so Tailwind opacity modifiers work. */
:root {
${block(light)}

  /* shape scale */
  --md-sys-shape-extra-small: 4px;
  --md-sys-shape-small: 8px;
  --md-sys-shape-medium: 12px;
  --md-sys-shape-large: 16px;
  --md-sys-shape-extra-large: 28px;
  --md-sys-shape-full: 9999px;

  /* elevation (tonal surfaces carry most of it; shadows only for floating layers) */
  --md-sys-elevation-1: 0 1px 2px rgb(0 0 0 / 0.30), 0 1px 3px 1px rgb(0 0 0 / 0.15);
  --md-sys-elevation-2: 0 1px 2px rgb(0 0 0 / 0.30), 0 2px 6px 2px rgb(0 0 0 / 0.15);
  --md-sys-elevation-3: 0 1px 3px rgb(0 0 0 / 0.30), 0 4px 8px 3px rgb(0 0 0 / 0.15);

  /* state layers */
  --md-sys-state-hover: 0.08;
  --md-sys-state-focus: 0.10;
  --md-sys-state-pressed: 0.10;

  /* motion */
  --md-sys-motion-easing-standard: cubic-bezier(0.2, 0, 0, 1);
  --md-sys-motion-duration-short: 150ms;
  --md-sys-motion-duration-medium: 250ms;
}

[data-theme='dark'] {
${block(dark)}
}
`
writeFileSync(join(here, '../src/m3.css'), css)

const hexOf = (sch) => Object.fromEntries(Object.entries(sch).map(([k, v]) => [k.replace(/-([a-z])/g, (_, c) => c.toUpperCase()), hexFromArgb(v)]))
const ts = `// GENERATED by scripts/m3_theme.mjs (seed ${SEED}). Light-scheme hex mirror of src/m3.css for maplibre paint and Recharts props.
export const M3 = ${JSON.stringify(hexOf(light), null, 2)} as const
`
writeFileSync(join(here, '../src/lib/m3.ts'), ts)
console.log('wrote src/m3.css and src/lib/m3.ts')
for (const k of ['primary', 'primary-container', 'secondary', 'tertiary', 'tertiary-container', 'error', 'error-container', 'low', 'low-container', 'low-fill', 'watch', 'watch-container', 'watch-fill', 'act', 'act-container', 'act-fill', 'surface', 'surface-container-low', 'surface-container', 'outline', 'outline-variant']) console.log(k.padEnd(26), hexFromArgb(light[k]))

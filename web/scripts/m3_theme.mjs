// Generates the Material 3 (Material You) colour tokens for AnnaDrishti.
//   node scripts/m3_theme.mjs        ->  src/m3.css  (CSS variables, light + [data-theme=dark])
//                                        src/lib/m3.ts (light hex mirror for maplibre / Recharts, which cannot read CSS vars)
// Algorithm: @material/material-color-utilities (HCT, tonal spot scheme) from the seed below.
// Semantic risk colours are M3 "custom colors" harmonised to the seed: low = green, watch = amber, act = M3 error.
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

// custom colours (harmonised toward the seed hue); source hex is the "natural" colour
const CUSTOM = [
  { name: 'low', value: argbFromHex('#2E8B57'), blend: true }, // green: low risk
  { name: 'watch', value: argbFromHex('#F0A500'), blend: true }, // amber: watch
]
// Brighter tone used for map fills, lamps, chart marks (tone 40 is for text/filled chips; marks need to read as the hue)
const FILL_TONE = { low: 50, watch: 72, act: 42 }

function buildScheme(dark) {
  const s = new SchemeTonalSpot(Hct.fromInt(seed), dark, 0)
  const out = {}
  for (const [k, c] of Object.entries(ROLES)) out[k] = c.getArgb(s)
  for (const cc of CUSTOM) {
    const g = customColor(seed, cc)
    const grp = dark ? g.dark : g.light
    out[cc.name] = grp.color
    out[`on-${cc.name}`] = grp.onColor
    out[`${cc.name}-container`] = grp.colorContainer
    out[`on-${cc.name}-container`] = grp.onColorContainer
    const hue = Hct.fromInt(Blend.harmonize(cc.value, seed))
    out[`${cc.name}-fill`] = TonalPalette.fromHueAndChroma(hue.hue, Math.max(hue.chroma, 48)).tone(dark ? FILL_TONE[cc.name] + 8 : FILL_TONE[cc.name])
  }
  const errHue = Hct.fromInt(out.error)
  out['act-fill'] = TonalPalette.fromHueAndChroma(errHue.hue, Math.max(errHue.chroma, 60)).tone(dark ? 60 : FILL_TONE.act)
  // semantic aliases (act = M3 error; nodata = outline-variant)
  out.act = out.error; out['on-act'] = out['on-error']; out['act-container'] = out['error-container']; out['on-act-container'] = out['on-error-container']
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
  ['on-low-container', 'low-container'], ['on-watch-container', 'watch-container'], ['on-error-container', 'error-container'],
  ['on-low', 'low'], ['on-watch', 'watch'], ['on-error', 'error'],
  ['on-low-container', 'surface-container-low'], ['on-watch-container', 'surface-container-low'], ['on-error-container', 'surface-container-low'],
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
for (const k of ['low-fill', 'watch-fill', 'act-fill']) console.log(`  ${k} ${hexFromArgb(light[k])} vs surface-container-low ${ratio(light[k], light['surface-container-low']).toFixed(2)}:1`)
if (bad) process.exit(1)

// ---------------------------------------------------------------- emit
const rgb = (a) => `${(a >> 16) & 255} ${(a >> 8) & 255} ${a & 255}`
// custom colours (low / watch / act / nodata and their fills) live in the M3 extended namespace
const EXT = /^(on-)?(low|watch|act|nodata)(-|$)|-fill$/
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
for (const k of ['primary', 'primary-container', 'secondary', 'tertiary', 'tertiary-container', 'error', 'error-container', 'low', 'low-container', 'low-fill', 'watch', 'watch-container', 'watch-fill', 'act-fill', 'surface', 'surface-container-low', 'surface-container', 'outline', 'outline-variant']) console.log(k.padEnd(26), hexFromArgb(light[k]))

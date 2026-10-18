import { splitTables } from './Markdown'

const HEAD_ECON = /cost|econom|profit|return|margin|income|₹|price|money|खर्च|लागत|खर्चा|ఖర్చు/i
const clip = (s: string, n = 240) => (s.length > n ? `${s.slice(0, n - 1).replace(/[\s,;:]+\S*$/, '')}…` : s)

/**
 * Farmer advice should not carry a cost table. Removes markdown tables (and the cost heading just above one); all
 * bullets and prose stay as written. The table's figures come back as one short muted line.
 */
export function splitEconomics(md: string): { body: string; econ: string | null } {
  const pieces: string[] = []
  const out: string[] = []
  for (const seg of splitTables(md)) {
    if (seg.kind === 'table') {
      const rows = seg.rows.slice(0, 4).map((r) => `${r[0]}: ${r.slice(1).filter((c) => /\d/.test(c)).join(' / ')}`.replace(/:\s*$/, ''))
      if (rows.length) pieces.push(rows.join('; '))
      // drop an orphaned heading / lead-in line right above the table
      while (out.length && out[out.length - 1].trim() === '') out.pop()
      if (out.length && (/^\s*#{1,6}\s/.test(out[out.length - 1]) || /:\s*$/.test(out[out.length - 1])) && HEAD_ECON.test(out[out.length - 1])) out.pop()
      continue
    }
    out.push(...seg.text.split('\n'))
  }
  const body = out.join('\n').replace(/\n{3,}/g, '\n\n').trim()
  const econ = pieces.length ? clip(pieces.join(' · ')) : null
  return { body, econ }
}

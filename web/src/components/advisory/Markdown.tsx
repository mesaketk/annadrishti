import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'

// Self-contained typography so briefings read well regardless of global .md styles.
const components: Components = {
  h1: (p) => <h3 className="mb-2 mt-5 md-title-large text-on-surface first:mt-0" {...p} />,
  h2: (p) => <h4 className="mb-1.5 mt-5 md-title-medium text-on-surface first:mt-0" {...p} />,
  h3: (p) => <h5 className="mb-1 mt-4 md-title-small text-on-surface first:mt-0" {...p} />,
  p: (p) => <p className="my-2 md-body text-on-surface" {...p} />,
  ul: (p) => <ul className="my-2 list-disc space-y-1 pl-5 md-body text-on-surface marker:text-primary" {...p} />,
  ol: (p) => <ol className="my-2 list-decimal space-y-1 pl-5 md-body text-on-surface marker:font-medium marker:text-primary" {...p} />,
  strong: (p) => <strong className="font-semibold text-on-surface" {...p} />,
  blockquote: (p) => <blockquote className="my-3 rounded-r-m3-sm border-l-4 border-watch-fill bg-watch-soft px-3 py-2 md-body-medium text-watch-ink" {...p} />,
  a: (p) => <a className="font-medium text-primary underline" target="_blank" rel="noopener noreferrer" {...p} />,
  hr: () => <hr className="my-4 border-outline-variant" />,
  table: (p) => <div className="my-3 overflow-x-auto"><table className="w-full border-collapse md-body-medium" {...p} /></div>,
  th: (p) => <th className="border border-outline-variant bg-surface-container px-2 py-1 text-left font-medium" {...p} />,
  td: (p) => <td className="border border-outline-variant px-2 py-1 align-top" {...p} />,
  code: (p) => <code className="rounded-m3-xs bg-surface-container px-1 md-body-medium" {...p} />,
}
// react-markdown without remark-gfm does not render pipe tables, so tables are split out and drawn here.
type Seg = { kind: 'md'; text: string } | { kind: 'table'; head: string[]; rows: string[][] }
const cells = (l: string) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim().replace(/\*\*/g, ''))
const isRow = (l: string) => /^\s*\|.*\|\s*$/.test(l)
const isSep = (l: string) => isRow(l) && /-{3,}/.test(l) && /^[\s|:-]+$/.test(l)
export function splitTables(md: string): Seg[] {
  // models sometimes flatten a whole table onto one line: restore the row breaks
  const lines = md.split('\n').flatMap((l) => (isRow(l) && /\|\s*-{3,}/.test(l) && /\|\s+\|/.test(l) ? l.replace(/\|\s+\|/g, '|\n|').split('\n') : [l]))
  const out: Seg[] = []
  let buf: string[] = []
  const flush = () => { if (buf.length) out.push({ kind: 'md', text: buf.join('\n') }); buf = [] }
  for (let i = 0; i < lines.length; i++) {
    if (isRow(lines[i]) && i + 1 < lines.length && isSep(lines[i + 1])) {
      flush()
      const head = cells(lines[i]); const rows: string[][] = []
      i += 2
      while (i < lines.length && isRow(lines[i])) rows.push(cells(lines[i++]))
      i--
      out.push({ kind: 'table', head, rows })
    } else buf.push(lines[i])
  }
  flush()
  return out
}

export default function Markdown({ children, large = false, lang }: { children: string; large?: boolean; lang?: string }) {
  return (
    <div lang={lang} data-large={large || undefined}>
      {splitTables(children).map((s, i) => s.kind === 'md'
        ? <ReactMarkdown key={i} components={components}>{s.text}</ReactMarkdown>
        : (
          <div key={i} className="my-3 overflow-x-auto rounded-m3-md border border-outline-variant">
            <table className="w-full border-collapse md-body-medium">
              <thead><tr>{s.head.map((h, j) => <th key={j} className="border-b border-outline-variant bg-surface-container px-3 py-2 text-left font-medium">{h}</th>)}</tr></thead>
              <tbody>{s.rows.map((r, j) => <tr key={j} className="even:bg-surface-container-low">{r.map((c, k) => <td key={k} className="border-t border-outline-variant px-3 py-2 align-top">{c}</td>)}</tr>)}</tbody>
            </table>
          </div>
        ))}
    </div>
  )
}

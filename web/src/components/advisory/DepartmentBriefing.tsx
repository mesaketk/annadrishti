import { useCallback, useEffect, useRef, useState } from 'react'
import { getAdvisory } from '../../lib/api'
import { DEPARTMENTS } from '../../lib/extra'
import { useStore } from '../../lib/store'
import type { Department, District } from '../../types'
import { Button, Card, ErrorNote, Pill, Skeleton, cx } from '../drawer/ui'
import { Chip, Icon } from '../ui'
import Markdown from './Markdown'

const cache = new Map<string, string>() // `${lgd}|${scenario}|${department}` -> markdown

/** Department briefing generator. With `department` set there is no selector; otherwise chips choose one. */
export default function DepartmentBriefing({ d, scenarioKey, department }: { d: District; scenarioKey: string; department?: Department }) {
  const mock = useStore((s) => s.mock)
  const [picked, setPicked] = useState<Department>('collector')
  const dept = department ?? picked
  const key = `${d.lgd}|${scenarioKey}|${dept}`
  const [, bump] = useState(0)
  const [loadingKey, setLoadingKey] = useState<string | null>(null)
  const [err, setErr] = useState<{ key: string; msg: string } | null>(null)
  const [copied, setCopied] = useState(false)
  const req = useRef(0)
  const md = cache.get(key) ?? null
  const loading = loadingKey === key
  const label = DEPARTMENTS.find((x) => x.id === dept)?.label ?? dept

  useEffect(() => { req.current++; setLoadingKey(null); setErr(null) }, [d.lgd, scenarioKey])

  const run = useCallback(async (force = false) => {
    if (force) cache.delete(key)
    if (cache.has(key)) { bump((n) => n + 1); return }
    const id = ++req.current
    setLoadingKey(key); setErr(null)
    try {
      cache.set(key, await getAdvisory(d, 'official', 'en', scenarioKey, mock, { department: dept }))
    } catch (e) {
      if (id === req.current) setErr({ key, msg: e instanceof Error ? e.message : 'Request failed' })
    } finally {
      if (id === req.current) setLoadingKey(null)
      bump((n) => n + 1)
    }
  }, [key, d, scenarioKey, mock, dept])

  const copy = async () => {
    if (!md) return
    try { await navigator.clipboard.writeText(md); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { /* clipboard blocked */ }
  }

  return (
    <Card title={<span className="flex flex-wrap items-center gap-2">Briefing for your department <Pill tone="accent">Written by Gemini</Pill></span>}>
      {!department && (
        <div className="mb-3" role="radiogroup" aria-label="Department">
          <div className="flex flex-wrap gap-2">
            {DEPARTMENTS.map((x) => {
              const on = x.id === dept
              return (
                <Chip key={x.id} role="radio" aria-checked={on} selected={on} onClick={() => setPicked(x.id)}
                  className={cx(!on && cache.has(`${d.lgd}|${scenarioKey}|${x.id}`) && '!border-primary/60')}>
                  {x.short}
                </Chip>
              )
            })}
          </div>
        </div>
      )}
      {!md && !loading && !(err?.key === key) && (
        <div>
          <p className="mb-3 md-body text-muted">A one-page plan for {d.district}, written for the {label} department: what is happening, what to do first and by when.</p>
          <Button onClick={() => void run()} className="w-full sm:w-auto" iconLeft={<Icon name="auto_awesome" size={20} />}>Write the {label} briefing</Button>
        </div>
      )}
      {loading && (
        <div className="space-y-2" aria-busy="true" aria-live="polite">
          <Skeleton className="h-4 w-2/3" /><Skeleton className="h-3 w-full" /><Skeleton className="h-3 w-11/12" /><Skeleton className="h-3 w-4/5" /><Skeleton className="h-3 w-full" />
          <p className="md-body-small text-muted">Reading the district evidence…</p>
        </div>
      )}
      {err?.key === key && <ErrorNote onRetry={() => void run(true)}>Could not write the briefing: {err.msg}</ErrorNote>}
      {md && (
        <div>
          <div className="mb-2 rounded-m3-sm bg-primary-container px-3 py-1.5 md-label-large text-on-primary-container" data-testid="brief-header">Briefing for: {label}</div>
          <Markdown>{md}</Markdown>
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-outline-variant pt-3">
            <Button variant="secondary" onClick={copy} iconLeft={<Icon name={copied ? 'check' : 'content_copy'} size={18} />}>{copied ? 'Copied' : 'Copy text'}</Button>
            <Button variant="ghost" onClick={() => void run(true)} className="ml-auto">Write it again</Button>
          </div>
        </div>
      )}
    </Card>
  )
}

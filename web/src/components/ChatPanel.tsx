import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { useStore } from '../lib/store'
import { useRoute } from '../lib/route'
import { chat } from '../lib/api'
import { useScenario } from '../lib/useScenario'
import { useMedia } from '../lib/useMedia'
import type { ChatMsg } from '../types'
import { AiBadge, Button, Chip, Icon, IconButton, LinearProgress, Sheet } from './ui'

/** Suggested questions per role. */
const SUGGESTIONS: Record<'farmer' | 'officer' | 'planner', string[]> = {
  farmer: ['What should I sow this season?', 'Should I buy crop insurance?', 'When should I sow?'],
  officer: ['Who is most at risk in my district?', 'What should my department do first?'],
  planner: ['Which districts should pre-position pulses first?'],
}

/** Spark: gradient extended FAB with a slow sheen (the sheen is switched off by prefers-reduced-motion). */
function SparkFab({ onClick, collapsed, className }: { onClick: () => void; collapsed?: boolean; className?: string }) {
  return (
    <button
      type="button" onClick={onClick} aria-label={collapsed ? 'Spark: ask a question' : undefined} title={collapsed ? 'Spark · Ask a question (powered by Gemini)' : 'Powered by Gemini'}
      className={`md-state ai-gradient ai-sheen inline-flex h-14 items-center justify-center gap-3 rounded-m3-lg md-label-large shadow-elev-3 transition-shadow hover:shadow-elev-3 ${collapsed ? 'w-14' : 'pl-3 pr-5'} ${className ?? ''}`}
    >
      {collapsed ? <Icon name="auto_awesome" fill /> : <><AiBadge feature="spark" variant="glass" size="md" />Ask a question</>}
    </button>
  )
}

export default function ChatPanel() {
  const { chatOpen, setChatOpen, districts, mock, byLgd, select, myLgd, selected, view } = useStore()
  const route = useRoute()
  const { gkey, label: scLabel } = useScenario()
  const wide = useMedia('(min-width: 768px)')
  const drawerOpen = useMedia('(min-width: 1024px)') && route === 'planner' && selected != null && view === 'map'
  const [msgs, setMsgs] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [msgs, busy, chatOpen])
  const role = route === 'root' ? 'planner' : route
  // the district the question is about: the selected one on the planner map, "my district" on the farmer and officer pages
  const ctxLgd = role === 'planner' ? selected : myLgd ?? selected
  const ctxDistrict = ctxLgd != null ? byLgd.get(ctxLgd) : undefined
  const [ctxOff, setCtxOff] = useState<number | null>(null) // district the user dismissed as context
  const about = ctxDistrict && ctxOff !== ctxDistrict.lgd ? ctxDistrict : undefined
  const sugg = SUGGESTIONS[role]
  const awaiting = msgs[msgs.length - 1]?.clarify === true

  const send = async (text: string) => {
    const t = text.trim()
    if (!t || busy) return
    const next: ChatMsg[] = [...msgs, { role: 'user', content: t }]
    setMsgs(next); setInput(''); setBusy(true); setErr(null)
    try {
      const r = await chat(next, gkey, districts, mock, { lgd: about?.lgd ?? null, role })
      setMsgs([...next, { role: 'assistant', content: r.reply || 'I could not find an answer to that. Try asking in a different way.', citations: r.citations, clarify: r.clarify, options: r.options }])
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Request failed')
    } finally { setBusy(false) }
  }

  const body = (
    <>
      {about && (
          <div className="flex shrink-0 items-center gap-1 px-3 pt-1">
            <span className="inline-flex h-8 items-center gap-1.5 rounded-m3-sm bg-secondary-container pl-2.5 pr-1 md-label-large text-on-secondary-container" title="Questions are answered about this district">
              <Icon name="my_location" size={18} />About: {about.district}
              <button type="button" aria-label={`Stop asking about ${about.district}`} title="Ask about all of India" onClick={() => setCtxOff(about.lgd)} className="md-state ml-0.5 grid h-6 w-6 place-items-center rounded-full"><Icon name="close" size={16} /></button>
            </span>
          </div>
      )}
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {msgs.length === 0 && (
          <div className="space-y-3">
            <div className="md-body-medium text-muted">Try asking:</div>
            <div className="flex flex-col items-start gap-2">
              {sugg.map((s) => (
                <Chip key={s} size="lg" onClick={() => send(s)}>{s}</Chip>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'flex justify-end' : ''}>
            <div className={`max-w-[92%] px-4 py-3 md-body-medium ${m.role === 'user' ? 'rounded-m3-lg rounded-br-m3-xs bg-primary text-on-primary' : 'rounded-m3-lg rounded-bl-m3-xs bg-surface-container-high text-on-surface'}`}>
              {m.clarify && <div className="mb-1 flex items-center gap-1 md-label-medium text-muted"><Icon name="help" size={16} />One quick question</div>}
              {m.role === 'user' ? m.content : <div className="md"><ReactMarkdown>{m.content}</ReactMarkdown></div>}
              {m.clarify && i === msgs.length - 1 && (
                m.options?.length
                  ? <div className="mt-3 flex flex-wrap gap-2">{m.options.map((o) => <Chip key={o} onClick={() => send(o)}>{o}</Chip>)}</div>
                  : <div className="mt-2 md-body-small text-muted">Type your answer below.</div>
              )}
              {m.citations && m.citations.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2 border-t border-outline-variant pt-3">
                  {m.citations.map((l) => byLgd.get(l) && (
                    <Chip key={l} onClick={() => { select(l, true); if (route === 'planner') useStore.getState().setView('map') }}>
                      {byLgd.get(l)!.district}
                    </Chip>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="w-44 space-y-2 rounded-m3-lg rounded-bl-m3-xs bg-surface-container-high px-4 py-3 md-body-medium text-muted"><span>Thinking…</span><LinearProgress label="Thinking" /></div>}
        {err && <div role="alert" className="rounded-m3-md bg-error-container p-3 md-body-medium text-on-error-container">Could not answer: {err}</div>}
        <div ref={end} />
      </div>
      <form onSubmit={(e) => { e.preventDefault(); void send(input) }} className="flex items-center gap-2 p-3 pt-4">
        <label className="md-field min-w-0 flex-1" style={{ '--md-field-bg': 'rgb(var(--md-rgb-surface-container-high))' } as React.CSSProperties}>
          <span className="md-field-label md-body-small">{awaiting ? 'Your answer' : 'Your question'}</span>
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={awaiting ? 'Type your answer…' : 'Type your question…'} className="md-control md-body-large" />
        </label>
        <Button variant="primary" type="submit" disabled={busy || !input.trim()} aria-label="Send" title="Send" className="w-12 shrink-0 !px-0"><Icon name="send" fill size={22} /></Button>
      </form>
    </>
  )

  const pos = drawerOpen ? 'right-[444px]' : 'right-4'
  if (!wide) {
    return (
      <>
        {!chatOpen && (
          <SparkFab collapsed={route !== 'farmer'} onClick={() => setChatOpen(true)} className={`fixed right-4 z-30 ${route === 'farmer' ? 'bottom-24' : 'bottom-4'}`} />
        )}
        <Sheet open={chatOpen} onClose={() => setChatOpen(false)} side="bottom" title={<span className="inline-flex items-center gap-2"><AiBadge feature="spark" size="md" />Ask a question</span>} ariaLabel="Spark: ask a question" widthClass="">
          <div className="flex h-[70dvh] flex-col bg-surface-container-high">
            <div className="px-4 pb-1 md-body-small text-muted">Answers use the district data · {scLabel}</div>
            {body}
          </div>
        </Sheet>
      </>
    )
  }
  if (!chatOpen) {
    return (
      <SparkFab onClick={() => setChatOpen(true)} className={`fixed bottom-12 ${pos} z-30`} />
    )
  }
  return (
    <div className={`fixed bottom-12 ${pos} z-30 flex h-[min(520px,66vh)] w-[380px] flex-col overflow-hidden rounded-m3-xl bg-surface-container-high shadow-elev-3`}>
      <div className="flex items-center justify-between px-4 pb-2 pt-3">
        <div>
          <div className="flex items-center gap-2 md-title-large"><AiBadge feature="spark" size="md" />Ask a question</div>
          <div className="md-body-small text-muted">Answers use the district data · {scLabel}</div>
        </div>
        <IconButton icon="close" label="Close" onClick={() => setChatOpen(false)} />
      </div>
      {body}
    </div>
  )
}

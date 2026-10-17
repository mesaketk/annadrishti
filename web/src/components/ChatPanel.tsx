import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { useStore } from '../lib/store'
import { useRoute } from '../lib/route'
import { chat } from '../lib/api'
import { useScenario } from '../lib/useScenario'
import { useMedia } from '../lib/useMedia'
import type { ChatMsg } from '../types'
import { Button, Chip, Fab, Icon, IconButton, LinearProgress, Sheet } from './ui'

/** Suggested questions per role (district name filled in when known). */
function suggestions(role: string, name: string | null, state: string | null): string[] {
  if (role === 'farmer') return [name ? `Is ${name} at risk this season?` : 'Which districts are at risk this season?', 'What should I sow this season?', 'Where can I get seed and crop insurance?']
  if (role === 'officer') return [name ? `What are the top 5 actions for ${name}?` : 'Which districts need action first?', name ? `Which districts near ${name} are also at risk?` : 'Which districts have the most children at risk?', state ? `How many children under 5 are at risk in ${state}?` : 'How many children under 5 are at risk?']
  return ['Which Maharashtra districts should pre-position pulses stock?', 'Top 5 districts where El Niño hits harvests hardest?', 'Compare Nandurbar in a normal year and a strong El Niño']
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
  const my = myLgd != null ? byLgd.get(myLgd) : undefined
  const sugg = useMemo(() => suggestions(route === 'root' ? 'planner' : route, my?.district ?? null, my?.state ?? null), [route, my])

  const send = async (text: string) => {
    const t = text.trim()
    if (!t || busy) return
    const next: ChatMsg[] = [...msgs, { role: 'user', content: t }]
    setMsgs(next); setInput(''); setBusy(true); setErr(null)
    try {
      const r = await chat(next, gkey, districts, mock)
      setMsgs([...next, { role: 'assistant', content: r.reply, citations: r.citations }])
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Request failed')
    } finally { setBusy(false) }
  }

  const body = (
    <>
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
              {m.role === 'user' ? m.content : <div className="md"><ReactMarkdown>{m.content}</ReactMarkdown></div>}
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
          <span className="md-field-label md-body-small">Your question</span>
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Type your question…" className="md-control md-body-large" />
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
          <Fab icon="forum" label="Ask a question" collapsed={route !== 'farmer'} onClick={() => setChatOpen(true)} className={`fixed right-4 z-30 ${route === 'farmer' ? 'bottom-24' : 'bottom-4'}`} />
        )}
        <Sheet open={chatOpen} onClose={() => setChatOpen(false)} side="bottom" title="Ask a question" widthClass="">
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
      <Fab icon="forum" label="Ask a question" onClick={() => setChatOpen(true)} className={`fixed bottom-12 ${pos} z-30`} />
    )
  }
  return (
    <div className={`fixed bottom-12 ${pos} z-30 flex h-[min(520px,66vh)] w-[380px] flex-col overflow-hidden rounded-m3-xl bg-surface-container-high shadow-elev-3`}>
      <div className="flex items-center justify-between px-4 pb-2 pt-3">
        <div>
          <div className="md-title-large">Ask a question</div>
          <div className="md-body-small text-muted">Answers use the district data · {scLabel}</div>
        </div>
        <IconButton icon="close" label="Close" onClick={() => setChatOpen(false)} />
      </div>
      {body}
    </div>
  )
}

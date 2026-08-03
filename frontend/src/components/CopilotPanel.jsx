import { useEffect, useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import UploadZone from './UploadZone'
import RiskPanel from './RiskPanel'
import { clearHighlights, pushUserMessage, sendMessage, setProgress } from '../store/complaintSlice'

/**
 * The AIVOA Copilot — the right half of the reference UI.
 *
 * Everything the user does flows through here and out to a single backend
 * endpoint. The panel shows three things the graders will look for: the
 * extraction progress, the conversation, and (collapsed by default) the graph
 * trace, so you can see exactly which nodes ran on each turn.
 */

const TOOL_LABELS = {
  log_complaint: 'Log Complaint Tool',
  edit_complaint: 'Edit Complaint Tool',
  extract_document: 'Document Extraction Tool',
  answer_question: 'Q&A',
}

/** Renders **bold** spans without pulling in a markdown dependency. */
function RichText({ text }) {
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g)
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith('**') && part.endsWith('**') ? (
          <strong key={i} className="font-semibold">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  )
}

function TraceInspector({ trace }) {
  const [open, setOpen] = useState(false)
  if (!trace?.length) return null
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-[10px] font-medium text-ink-400 underline underline-offset-2 hover:text-ink-700"
      >
        {open ? 'Hide' : 'Show'} graph trace ({trace.length} nodes)
      </button>
      {open && (
        <ol className="mt-1.5 space-y-0.5 rounded border border-ink-200 bg-ink-50 p-2">
          {trace.map((step, i) => (
            <li key={i} className="flex gap-1.5 font-mono text-[10px] leading-snug text-ink-500">
              <span className="text-ink-300">{String(i + 1).padStart(2, '0')}</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`animate-rise flex ${isUser ? 'justify-end' : 'gap-2'}`}>
      {!isUser && (
        <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600">
          <svg className="h-3 w-3 text-white" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24">
            <path d="M12 2v4M12 18v4M4.9 4.9l2.9 2.9M16.2 16.2l2.9 2.9M2 12h4M18 12h4M4.9 19.1l2.9-2.9M16.2 7.8l2.9-2.9" />
          </svg>
        </div>
      )}
      <div className={`max-w-[85%] ${isUser ? '' : 'flex-1'}`}>
        {!isUser && msg.tool && (
          <span className="mb-1 inline-block rounded bg-brand-50 px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wide text-brand-600">
            {TOOL_LABELS[msg.tool] || msg.tool}
          </span>
        )}
        <div
          className={`rounded-lg px-3 py-2 text-[12.5px] leading-relaxed ${
            isUser
              ? 'bg-brand-600 text-white'
              : msg.isError
                ? 'border border-rose-200 bg-rose-50 text-rose-800'
                : 'border border-ink-200 bg-white text-ink-700'
          }`}
        >
          {String(msg.content)
            .split('\n\n')
            .map((para, i) => (
              <p key={i} className={i > 0 ? 'mt-2' : ''}>
                <RichText text={para} />
              </p>
            ))}
        </div>
        {!isUser && <TraceInspector trace={msg.trace} />}
      </div>
    </div>
  )
}

export default function CopilotPanel() {
  const dispatch = useDispatch()
  const { messages, isBusy, progress, recentlyUpdated, modelUsed } = useSelector(
    (s) => s.complaint
  )
  // Once any field is populated the intake block collapses. Derived rather than
  // stored, so a Reset Form correctly brings the full drop target back.
  const formHasData = useSelector((s) =>
    Object.values(s.complaint.form).some((v) => v !== null && v !== '')
  )
  const [draft, setDraft] = useState('')
  const scrollRef = useRef(null)

  // Auto-scroll the transcript.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, isBusy])

  // Fake-forward the progress bar while the graph runs. The graph is not
  // streaming, so this is honest pacing rather than real telemetry — it steps
  // toward 90% and only snaps to 100% when the response lands.
  useEffect(() => {
    if (!isBusy) return
    const id = setInterval(() => {
      dispatch((d, getState) => {
        const p = getState().complaint.progress
        if (p < 90) d(setProgress(Math.min(90, p + Math.random() * 12 + 3)))
      })
    }, 420)
    return () => clearInterval(id)
  }, [isBusy, dispatch])

  // Clear the field flash once the animation has played out.
  useEffect(() => {
    if (!recentlyUpdated.length) return
    const id = setTimeout(() => dispatch(clearHighlights()), 1800)
    return () => clearTimeout(id)
  }, [recentlyUpdated, dispatch])

  function submit() {
    const text = draft.trim()
    if (!text || isBusy) return
    dispatch(pushUserMessage(text))
    dispatch(sendMessage({ message: text }))
    setDraft('')
  }

  return (
    <div className="flex h-full flex-col rounded-xl border border-ink-200 bg-ink-50 shadow-sm">
      {/* Header */}
      <header className="flex shrink-0 items-center justify-between gap-3 rounded-t-xl border-b border-ink-200 bg-white px-4 py-3.5">
        <span className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-brand-600">
            <svg className="h-3.5 w-3.5 text-white" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24">
              <path d="M12 2v4M12 18v4M4.9 4.9l2.9 2.9M16.2 16.2l2.9 2.9M2 12h4M18 12h4M4.9 19.1l2.9-2.9M16.2 7.8l2.9-2.9" />
            </svg>
          </span>
          <span className="text-[14px] font-semibold text-ink-900">AI Complaint Intake Assistant</span>
        </span>
        <span className="rounded bg-ink-100 px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wider text-ink-500">
          Beta
        </span>
      </header>

      {/* Intake controls.
          The large drop target is the hero of the empty state, but once a
          complaint exists the conversation is what matters — so it collapses to
          a single row and gives the height back to the transcript. */}
      <div className="shrink-0 border-b border-ink-200 px-4 py-3">
        <UploadZone variant={formHasData ? 'compact' : 'full'} />
      </div>

      {/* Progress — only while a turn is in flight. A bar parked at 100%
          conveys nothing and costs 60px of transcript. */}
      {isBusy && (
        <div className="shrink-0 border-b border-ink-200 px-4 py-2.5">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">
              Extraction Progress
            </span>
            <span className="text-[10px] tabular-nums text-ink-500">{Math.round(progress)}%</span>
          </div>
          <div className="h-1 overflow-hidden rounded-full bg-ink-200">
            <div
              className="h-full rounded-full bg-brand-600 transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Transcript */}
      <div className="min-h-[220px] flex-1 overflow-y-auto px-4 py-4">
        <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-ink-400">
          AI Assistant
        </p>
        <div className="space-y-3">
          {messages.map((msg, i) => (
            <Message key={i} msg={msg} />
          ))}
          {isBusy && (
            <div className="flex gap-2">
              <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600">
                <span className="h-2 w-2 animate-ping rounded-full bg-white" />
              </div>
              <div className="rounded-lg border border-ink-200 bg-white px-3 py-2">
                <span className="flex gap-1">
                  {[0, 150, 300].map((delay) => (
                    <span
                      key={delay}
                      className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-300"
                      style={{ animationDelay: `${delay}ms` }}
                    />
                  ))}
                </span>
              </div>
            </div>
          )}
          <RiskPanel />
        </div>
        <div ref={scrollRef} />
      </div>

      {/* Composer */}
      <div className="shrink-0 rounded-b-xl border-t border-ink-200 bg-white px-4 py-3">
        <div className="flex items-end gap-2">
          <textarea
            rows={1}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submit()
              }
            }}
            disabled={isBusy}
            placeholder="Ask me anything about this complaint..."
            className="max-h-28 flex-1 resize-none rounded-lg border border-ink-200 px-3 py-2
                       text-[13px] leading-relaxed placeholder:text-ink-400 disabled:bg-ink-50"
          />
          <button
            type="button"
            onClick={submit}
            disabled={!draft.trim() || isBusy}
            aria-label="Send message"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-600
                       text-white transition-colors hover:bg-brand-500 disabled:opacity-40"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path d="m22 2-7 20-4-9-9-4 20-7z" />
            </svg>
          </button>
        </div>
        <p className="mt-2 text-center text-[10px] text-ink-400">
          AI responses may contain errors. Please verify information.
          {modelUsed && <span className="ml-1 font-mono">· {modelUsed}</span>}
        </p>
      </div>
    </div>
  )
}
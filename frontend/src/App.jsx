import { useEffect, useRef } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import ComplaintForm from './components/ComplaintForm'
import CopilotPanel from './components/CopilotPanel'
import { bootstrap, dismissError } from './store/complaintSlice'

/**
 * Two-panel shell. Form left, copilot right, exactly as the reference UI.
 *
 * On mobile the panels stack with the copilot first, because on a phone the
 * assistant is the thing you interact with and the form is the thing you read
 * back — reversing them on small screens keeps the input above the fold.
 */
export default function App() {
  const dispatch = useDispatch()
  const { bootstrapped, error } = useSelector((s) => s.complaint)
  const didBootstrap = useRef(false)

  // React StrictMode deliberately runs effects twice in development. Without
  // this guard that opens two complaints per page load — the second is an
  // orphaned Draft row, and both requests race for the same complaint number.
  useEffect(() => {
    if (didBootstrap.current) return
    didBootstrap.current = true
    dispatch(bootstrap())
  }, [dispatch])

  return (
    <div className="min-h-screen bg-ink-100">
      {/* Top bar */}
      <header className="border-b border-ink-200 bg-white">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between px-5 py-3">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-ink-900">
              <span className="text-[11px] font-bold text-white">A</span>
            </span>
            <div>
              <p className="text-[13px] font-semibold leading-none text-ink-900">
                AIVOA <span className="font-normal text-ink-500">Quality Management System</span>
              </p>
              <p className="mt-1 text-[10.5px] leading-none text-ink-400">
                Customer Complaint Module · API &amp; FDF Manufacturing
              </p>
            </div>
          </div>
          <span className="hidden items-center gap-1.5 text-[11px] text-ink-500 sm:flex">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            {bootstrapped ? 'Connected' : 'Connecting…'}
          </span>
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="mx-auto max-w-[1500px] px-5 pt-3">
          <div
            role="alert"
            className="flex items-start justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-2.5"
          >
            <p className="text-[12.5px] text-rose-800">{error}</p>
            <button
              type="button"
              onClick={() => dispatch(dismissError())}
              className="shrink-0 text-[11px] font-medium text-rose-700 underline underline-offset-2"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Panels */}
      <main className="mx-auto max-w-[1500px] px-5 py-5">
        <div className="flex flex-col-reverse gap-5 lg:grid lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)] lg:items-stretch">
          <div className="lg:h-[calc(100vh-118px)]">
            <ComplaintForm />
          </div>
          <div className="lg:h-[calc(100vh-118px)]">
            <CopilotPanel />
          </div>
        </div>
      </main>
    </div>
  )
}
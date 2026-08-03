import { useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { pushUserMessage, sendMessage } from '../store/complaintSlice'

const ACCEPTED = '.pdf,.docx,.txt,.eml,.md'
const MAX_MB = 10

/**
 * Document intake. Two routes to the same graph node:
 *   - drop or pick a file  → multipart upload, backend extracts the text layer
 *   - paste text           → same endpoint, text goes straight to the tool
 *
 * The paste route exists because scanned complaint letters have no text layer,
 * and the brief waives production OCR. Rather than failing on those, we give
 * the user a way through.
 *
 * Two variants. `full` is the empty-state hero: a large drop target, because
 * uploading is the primary action when nothing has been logged yet. `compact`
 * is a single slim row used once a complaint exists, when the conversation
 * matters more than the upload affordance. Drag-and-drop works in both.
 */
export default function UploadZone({ variant = 'full' }) {
  const dispatch = useDispatch()
  const isBusy = useSelector((s) => s.complaint.isBusy)
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [pasting, setPasting] = useState(false)
  const [pastedText, setPastedText] = useState('')
  const [localError, setLocalError] = useState(null)

  function handleFile(file) {
    if (!file) return
    setLocalError(null)

    const ext = '.' + file.name.split('.').pop().toLowerCase()
    if (!ACCEPTED.split(',').includes(ext)) {
      setLocalError(`Cannot read ${ext} files. Accepted: PDF, DOCX, TXT, EML.`)
      return
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setLocalError(`That file is ${(file.size / 1024 / 1024).toFixed(1)} MB. Limit is ${MAX_MB} MB.`)
      return
    }

    dispatch(pushUserMessage(`Uploaded document: ${file.name}`))
    dispatch(sendMessage({ message: '', file }))
  }

  function submitPastedText() {
    const text = pastedText.trim()
    if (!text) return
    dispatch(pushUserMessage(text.length > 240 ? `${text.slice(0, 240)}…` : text))
    dispatch(sendMessage({ message: text }))
    setPastedText('')
    setPasting(false)
  }

  const dropHandlers = {
    onDragOver: (e) => {
      e.preventDefault()
      setDragging(true)
    },
    onDragLeave: () => setDragging(false),
    onDrop: (e) => {
      e.preventDefault()
      setDragging(false)
      handleFile(e.dataTransfer.files?.[0])
    },
  }

  const hiddenInput = (
    <input
      ref={inputRef}
      type="file"
      accept={ACCEPTED}
      className="hidden"
      onChange={(e) => {
        handleFile(e.target.files?.[0])
        e.target.value = ''
      }}
    />
  )

  const pasteBox = pasting && (
    <div className="animate-rise mt-2 space-y-2">
      <textarea
        autoFocus
        rows={variant === 'full' ? 5 : 4}
        value={pastedText}
        onChange={(e) => setPastedText(e.target.value)}
        placeholder="Paste the complaint letter or email body here..."
        className="w-full resize-none rounded-lg border border-ink-200 bg-white px-3 py-2
                   text-[13px] leading-relaxed placeholder:text-ink-400"
      />
      <div className="flex gap-2">
        <button
          type="button"
          onClick={submitPastedText}
          disabled={!pastedText.trim() || isBusy}
          className="flex-1 rounded-md bg-brand-600 px-3 py-2 text-[13px] font-medium
                     text-white transition-colors hover:bg-brand-500 disabled:opacity-40"
        >
          Extract Details
        </button>
        <button
          type="button"
          onClick={() => {
            setPasting(false)
            setPastedText('')
          }}
          className="rounded-md border border-ink-200 px-3 py-2 text-[13px] text-ink-700
                     transition-colors hover:bg-ink-50"
        >
          Cancel
        </button>
      </div>
    </div>
  )

  const errorNote = localError && (
    <p className="mt-2 rounded-md bg-rose-50 px-3 py-2 text-[11px] text-rose-700" role="alert">
      {localError}
    </p>
  )

  // ---------------------------------------------------------------- compact
  if (variant === 'compact') {
    return (
      <div {...dropHandlers}>
        <div
          className={`flex items-center gap-2 rounded-lg border px-2 py-1.5 transition-colors ${
            dragging ? 'border-brand-500 bg-brand-50' : 'border-ink-200 bg-white'
          }`}
        >
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={isBusy}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12px]
                       font-medium text-ink-700 transition-colors hover:bg-ink-100
                       disabled:opacity-50"
          >
            <svg className="h-3.5 w-3.5 text-brand-600" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
              <path d="M21.4 11.05 12.25 20.2a5.5 5.5 0 0 1-7.78-7.78l9.19-9.19a3.67 3.67 0 0 1 5.18 5.18l-9.2 9.19a1.83 1.83 0 0 1-2.59-2.59l8.49-8.48" />
            </svg>
            Attach document
          </button>

          <span className="h-4 w-px bg-ink-200" />

          <button
            type="button"
            onClick={() => setPasting((v) => !v)}
            disabled={isBusy}
            className="rounded-md px-2 py-1 text-[12px] font-medium text-ink-700
                       transition-colors hover:bg-ink-100 disabled:opacity-50"
          >
            Paste text
          </button>

          <span className="ml-auto pr-1 text-[10px] text-ink-400">
            {dragging ? 'Drop to upload' : 'PDF · DOCX · TXT · EML'}
          </span>
        </div>
        {hiddenInput}
        {pasteBox}
        {errorNote}
      </div>
    )
  }

  // ------------------------------------------------------------------- full
  return (
    <div className="space-y-3">
      <div
        {...dropHandlers}
        onClick={() => !isBusy && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            inputRef.current?.click()
          }
        }}
        role="button"
        tabIndex={0}
        aria-label="Upload a complaint document"
        className={`cursor-pointer rounded-lg border-2 border-dashed px-4 py-5 text-center
                    transition-colors ${
                      dragging
                        ? 'border-brand-500 bg-brand-50'
                        : 'border-ink-200 bg-ink-50 hover:border-brand-500 hover:bg-brand-50'
                    } ${isBusy ? 'pointer-events-none opacity-60' : ''}`}
      >
        <svg
          className="mx-auto mb-1.5 h-6 w-6 text-brand-500"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <path d="m17 8-5-5-5 5M12 3v13" />
        </svg>
        <p className="text-[13px] font-medium text-ink-700">
          Drag &amp; drop complaint document here
        </p>
        <p className="mt-0.5 text-xs text-brand-600 underline underline-offset-2">
          or click to browse
        </p>
        <p className="mt-1.5 text-[10.5px] text-ink-400">
          PDF · DOCX · TXT · EML · max {MAX_MB} MB
        </p>
        {hiddenInput}
      </div>

      <div className="flex items-center gap-3">
        <div className="h-px flex-1 bg-ink-200" />
        <span className="text-[10px] font-medium uppercase tracking-wider text-ink-400">or</span>
        <div className="h-px flex-1 bg-ink-200" />
      </div>

      {!pasting && (
        <button
          type="button"
          onClick={() => setPasting(true)}
          disabled={isBusy}
          className="w-full rounded-lg border border-ink-200 bg-white px-4 py-2 text-[13px]
                     font-medium text-ink-700 transition-colors hover:bg-ink-50 disabled:opacity-50"
        >
          Paste Complaint Text / Email
        </button>
      )}
      {pasteBox}
      {errorNote}
    </div>
  )
}
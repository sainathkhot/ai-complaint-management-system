import { useSelector } from 'react-redux'
import { selectHighlights } from '../store/complaintSlice'

/**
 * A single form field.
 *
 * Read-only by design. The assignment requires that the form is populated only
 * by the assistant, so there is no onChange handler anywhere in this component
 * — the value prop is the sole input, and it comes from Redux.
 *
 * When the field name appears in `recentlyUpdated`, it flashes blue. That is
 * what makes the demo legible: you can see at a glance which of the thirteen
 * fields the last instruction actually touched.
 */

function formatValue(value, type) {
  if (value === null || value === undefined || value === '') return null
  if (type === 'date') {
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return String(value)
    return d.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  }
  return String(value)
}

export default function Field({
  name,
  label,
  type = 'text',
  placeholder = 'Awaiting AI extraction...',
  suffix,
  rows,
}) {
  const value = useSelector((s) => s.complaint.form[name])
  const highlights = useSelector(selectHighlights)
  const isHot = highlights.includes(name)
  const display = formatValue(value, type)

  const boxClasses = [
    'field-box',
    rows ? 'whitespace-pre-wrap leading-relaxed' : 'truncate',
    display ? 'font-medium' : 'field-empty',
    isHot ? 'animate-fieldFlash' : '',
  ].join(' ')

  return (
    <div>
      <label className="field-label" htmlFor={`field-${name}`}>
        {label}
      </label>
      <div className="relative">
        <div
          id={`field-${name}`}
          className={boxClasses}
          style={rows ? { minHeight: `${rows * 20 + 16}px` } : undefined}
          title={display || placeholder}
          aria-readonly="true"
          role="textbox"
        >
          {display || placeholder}
        </div>
        {suffix && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] text-ink-400">
            {suffix}
          </span>
        )}
        {type === 'date' && !suffix && (
          <svg
            className="absolute right-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-300"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <rect x="3" y="4" width="18" height="18" rx="2" />
            <path d="M16 2v4M8 2v4M3 10h18" />
          </svg>
        )}
        {type === 'select' && (
          <svg
            className="absolute right-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-300"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        )}
      </div>
    </div>
  )
}

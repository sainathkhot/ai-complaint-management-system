import { useDispatch, useSelector } from 'react-redux'
import Field from './Field'
import { resetComplaint, saveComplaint } from '../store/complaintSlice'

/**
 * The "Log Customer Complaint" panel — the left half of the reference UI.
 *
 * Four sections mirroring the intake sequence a QA officer follows: where the
 * complaint came from, what product it concerns, what actually happened, and
 * how urgent it is.
 */

const STATUS_STYLES = {
  Draft: 'bg-ink-100 text-ink-500 ring-ink-200',
  'Pending Triage': 'bg-amber-50 text-amber-700 ring-amber-200',
  'Under Investigation': 'bg-brand-50 text-brand-600 ring-brand-100',
  Closed: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
}

function Section({ index, title, children, cols = 2 }) {
  return (
    <section className="mb-7">
      <h3 className="section-heading">
        {index}. {title}
      </h3>
      <div className={`grid gap-x-5 gap-y-4 ${cols === 2 ? 'sm:grid-cols-2' : 'grid-cols-1'}`}>
        {children}
      </div>
    </section>
  )
}

export default function ComplaintForm() {
  const dispatch = useDispatch()
  const { complaintNumber, status, isBusy, completeness } = useSelector((s) => s.complaint)

  return (
    <div className="flex h-full flex-col rounded-xl border border-ink-200 bg-white shadow-sm">
      {/* Header */}
      <header className="flex items-start justify-between gap-4 border-b border-ink-200 px-6 py-5">
        <div>
          <h2 className="text-[19px] font-semibold leading-tight text-ink-900">
            Log Customer Complaint
          </h2>
          <p className="mt-0.5 text-xs text-ink-500">
            API &amp; FDF Quality Assurance Module
            <span className="mx-1.5 text-ink-300">·</span>
            <span className="font-medium tabular-nums text-ink-700">{complaintNumber}</span>
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-3 py-1 text-[11px] font-medium ring-1 ring-inset ${
            STATUS_STYLES[status] || STATUS_STYLES.Draft
          }`}
        >
          {status}
        </span>
      </header>

      {/* Completeness strip — bonus feature, surfaced where it is useful */}
      {completeness.percent_complete > 0 && (
        <div className="flex items-center gap-3 border-b border-ink-200 bg-ink-50 px-6 py-2.5">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-ink-200">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                completeness.is_complete ? 'bg-emerald-500' : 'bg-brand-500'
              }`}
              style={{ width: `${completeness.percent_complete}%` }}
            />
          </div>
          <span className="shrink-0 text-[11px] tabular-nums text-ink-500">
            {completeness.percent_complete}% complete
          </span>
          {completeness.missing_mandatory_fields.length > 0 && (
            <span className="shrink-0 text-[11px] text-amber-600">
              {completeness.missing_mandatory_fields.length} required field
              {completeness.missing_mandatory_fields.length === 1 ? '' : 's'} missing
            </span>
          )}
        </div>
      )}

      {/* Fields */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <Section index="1" title="Origin & Customer Details">
          <Field name="complaint_source" label="Complaint Source" type="select" />
          <Field name="customer_name" label="Customer Name" />
        </Section>

        <Section index="2" title="Product & Batch Identification">
          <Field name="product_name" label="Product Name" />
          <Field name="product_strength" label="Product Strength/Grade" />
          <Field name="batch_lot_number" label="Batch/Lot Number" />
          <Field name="manufacturing_date" label="Manufacturing Date" type="date" />
          <Field name="expiry_date" label="Expiry Date" type="date" />
          <Field name="quantity_affected" label="Quantity Affected" />
        </Section>

        <Section index="3" title="Complaint Details">
          <Field name="complaint_type" label="Complaint Type" type="select" />
          <Field name="complaint_date" label="Complaint Date" type="date" />
          <div className="sm:col-span-2">
            <Field
              name="detailed_description"
              label="Detailed Complaint Description"
              rows={4}
            />
          </div>
        </Section>

        <Section index="4" title="Initial Assessment & Priority">
          <Field name="initial_severity" label="Initial Severity" type="select" />
          <Field name="priority" label="Priority" type="select" />
        </Section>
      </div>

      {/* Actions */}
      <footer className="flex items-center justify-between gap-3 border-t border-ink-200 px-6 py-4">
        <button
          type="button"
          onClick={() => dispatch(resetComplaint())}
          disabled={isBusy}
          className="inline-flex items-center gap-1.5 rounded-md border border-ink-200 bg-white
                     px-3.5 py-2 text-[13px] font-medium text-ink-700 transition-colors
                     hover:bg-ink-50 disabled:opacity-50"
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
            <path d="M3 3v5h5" />
          </svg>
          Reset Form
        </button>

        <button
          type="button"
          onClick={() => dispatch(saveComplaint())}
          disabled={isBusy}
          className="inline-flex items-center gap-1.5 rounded-md bg-brand-600 px-4 py-2
                     text-[13px] font-medium text-white shadow-sm transition-colors
                     hover:bg-brand-500 disabled:opacity-50"
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
            <path d="M17 21v-8H7v8M7 3v5h8" />
          </svg>
          Save Complaint
        </button>
      </footer>
    </div>
  )
}

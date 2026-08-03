import { useState } from 'react'
import { useSelector } from 'react-redux'

/**
 * AI Copilot Risk Assessment.
 *
 * Rendered from `state.risk`, which the `assess_risk` graph node rewrites on
 * every mutation of the form. Watching the severity change when the affected
 * quantity is corrected is the clearest demonstration that the assessment is
 * derived from the merged record rather than pasted in once at intake.
 */

const SEVERITY_STYLES = {
  Critical: 'bg-rose-50 text-rose-700 ring-rose-200',
  Major: 'bg-amber-50 text-amber-700 ring-amber-200',
  Minor: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
}

function scoreColor(score) {
  if (score >= 8) return 'bg-rose-500'
  if (score >= 6) return 'bg-amber-500'
  if (score >= 4) return 'bg-yellow-400'
  return 'bg-emerald-500'
}

function Row({ label, children }) {
  return (
    <div className="border-t border-ink-200 pt-2.5">
      <dt className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">
        {label}
      </dt>
      <dd className="mt-1 text-[12.5px] leading-relaxed text-ink-700">{children}</dd>
    </div>
  )
}

function BulletList({ items }) {
  return (
    <ul className="space-y-1">
      {items.map((item, i) => (
        <li key={i} className="flex gap-1.5">
          <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-ink-400" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

export default function RiskPanel() {
  const risk = useSelector((s) => s.complaint.risk)
  const duplicates = useSelector((s) => s.complaint.duplicates)
  const summary = useSelector((s) => s.complaint.summary)
  const [expanded, setExpanded] = useState(true)

  if (!risk.severity_classification && !risk.recommended_next_action) return null

  return (
    <div className="animate-rise rounded-lg border border-ink-200 bg-white">
      {/* Header */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left"
        aria-expanded={expanded}
      >
        <span className="flex items-center gap-2">
          <svg className="h-3.5 w-3.5 text-brand-600" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
          <span className="text-[12px] font-semibold text-ink-900">
            AI Copilot Risk Assessment
          </span>
        </span>
        <span className="flex items-center gap-2">
          {risk.severity_classification && (
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${
                SEVERITY_STYLES[risk.severity_classification] || SEVERITY_STYLES.Minor
              }`}
            >
              {risk.severity_classification}
            </span>
          )}
          <svg
            className={`h-3.5 w-3.5 text-ink-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        </span>
      </button>

      {expanded && (
        <dl className="space-y-2.5 px-3.5 pb-3.5">
          {/* Risk score bar */}
          {risk.risk_score != null && (
            <div className="border-t border-ink-200 pt-2.5">
              <div className="mb-1.5 flex items-baseline justify-between">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">
                  Risk Score
                </span>
                <span className="text-[13px] font-semibold tabular-nums text-ink-900">
                  {risk.risk_score}
                  <span className="text-[11px] font-normal text-ink-400">/10</span>
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-ink-100">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${scoreColor(risk.risk_score)}`}
                  style={{ width: `${risk.risk_score * 10}%` }}
                />
              </div>
            </div>
          )}

          {risk.recommended_next_action && (
            <Row label="Recommended Next Action">
              <span className="font-medium text-ink-900">{risk.recommended_next_action}</span>
            </Row>
          )}

          {risk.patient_safety_impact && (
            <Row label="Patient Safety Impact">{risk.patient_safety_impact}</Row>
          )}

          {risk.regulatory_reportable != null && (
            <Row label="Regulatory Reportable">
              <span
                className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                  risk.regulatory_reportable
                    ? 'bg-rose-50 text-rose-700'
                    : 'bg-ink-100 text-ink-600'
                }`}
              >
                {risk.regulatory_reportable
                  ? 'Yes — may require a Field Alert Report'
                  : 'No'}
              </span>
            </Row>
          )}

          {risk.potential_root_causes?.length > 0 && (
            <Row label="Potential Root Causes">
              <BulletList items={risk.potential_root_causes} />
            </Row>
          )}

          {risk.capa_recommendations?.length > 0 && (
            <Row label="CAPA Recommendations">
              <BulletList items={risk.capa_recommendations} />
            </Row>
          )}

          {risk.investigation_due_days != null && (
            <Row label="Investigation Target">
              Close within{' '}
              <span className="font-semibold tabular-nums">
                {risk.investigation_due_days} days
              </span>{' '}
              of receipt
            </Row>
          )}

          {risk.rationale && (
            <Row label="Assessment Rationale">
              <span className="italic text-ink-500">{risk.rationale}</span>
            </Row>
          )}

          {summary && <Row label="Complaint Summary">{summary}</Row>}

          {/* Duplicate detection — bonus feature */}
          {duplicates?.has_duplicates && (
            <div className="mt-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
              <p className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold text-amber-800">
                <svg className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24">
                  <path d="M12 9v4M12 17h.01" />
                  <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
                </svg>
                Possible duplicate complaint
              </p>
              <ul className="space-y-1">
                {duplicates.matches.map((m) => (
                  <li key={m.complaint_id} className="text-[11px] text-amber-800">
                    <span className="font-semibold tabular-nums">{m.complaint_number}</span>
                    {' — '}
                    {m.reason} ({m.similarity}% match)
                  </li>
                ))}
              </ul>
            </div>
          )}
        </dl>
      )}
    </div>
  )
}

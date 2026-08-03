/**
 * The complaint slice.
 *
 * Design note for the walkthrough: the form fields on the left are read-only
 * projections of `state.form`. Nothing in the UI writes to them directly —
 * the only way a value gets into this slice is through an AI response. That is
 * the assignment's "you must not fill the left form manually" rule enforced in
 * the state layer rather than by setting `disabled` on the inputs.
 *
 * `recentlyUpdated` holds the field names the last AI turn changed, so the UI
 * can flash them. It self-clears after the animation so a later unrelated
 * render doesn't re-trigger it.
 */

import { createAsyncThunk, createSlice } from '@reduxjs/toolkit'
import { api } from '../api/client'

export const EMPTY_FORM = {
  complaint_source: null,
  customer_name: null,
  product_name: null,
  product_strength: null,
  batch_lot_number: null,
  manufacturing_date: null,
  expiry_date: null,
  quantity_affected: null,
  complaint_type: null,
  complaint_date: null,
  detailed_description: null,
  initial_severity: null,
  priority: null,
}

const EMPTY_RISK = {
  severity_classification: null,
  risk_score: null,
  patient_safety_impact: null,
  regulatory_reportable: null,
  recommended_next_action: null,
  potential_root_causes: [],
  capa_recommendations: [],
  investigation_due_days: null,
  rationale: null,
}

const initialState = {
  complaintId: null,
  complaintNumber: '—',
  status: 'Draft',
  form: EMPTY_FORM,
  risk: EMPTY_RISK,
  completeness: { is_complete: false, missing_mandatory_fields: [], percent_complete: 0 },
  duplicates: { has_duplicates: false, matches: [] },
  summary: null,
  messages: [],
  recentlyUpdated: [],
  lastTrace: [],
  lastTool: null,
  modelUsed: null,
  progress: 0,
  phase: 'idle', // idle | thinking | done
  isBusy: false,
  error: null,
  bootstrapped: false,
}

// ---------------------------------------------------------------------------
// Thunks
// ---------------------------------------------------------------------------

export const bootstrap = createAsyncThunk('complaint/bootstrap', async () => {
  return api.createComplaint()
})

export const sendMessage = createAsyncThunk(
  'complaint/sendMessage',
  async ({ message, file }, { getState, rejectWithValue }) => {
    const id = getState().complaint.complaintId
    try {
      return await api.sendMessage(id, { message, file })
    } catch (err) {
      return rejectWithValue(err.message)
    }
  }
)

export const resetComplaint = createAsyncThunk(
  'complaint/reset',
  async (_, { getState }) => api.resetComplaint(getState().complaint.complaintId)
)

export const saveComplaint = createAsyncThunk(
  'complaint/save',
  async (_, { getState, rejectWithValue }) => {
    try {
      return await api.saveComplaint(getState().complaint.complaintId)
    } catch (err) {
      return rejectWithValue(err.message)
    }
  }
)

// ---------------------------------------------------------------------------
// Slice
// ---------------------------------------------------------------------------

/** Fold a server response into the slice. Shared by every fulfilled thunk. */
function applyServerState(state, payload, { recordUpdates = true } = {}) {
  state.complaintId = payload.complaint_id
  state.complaintNumber = payload.complaint_number
  state.status = payload.status
  state.form = { ...EMPTY_FORM, ...payload.form }
  state.risk = { ...EMPTY_RISK, ...payload.risk_assessment }
  state.completeness = payload.completeness || initialState.completeness
  state.duplicates = payload.duplicates || initialState.duplicates
  state.summary = payload.summary || null
  state.lastTrace = payload.trace || []
  state.lastTool = payload.tool_used || null
  state.modelUsed = payload.model_used || state.modelUsed
  state.recentlyUpdated = recordUpdates ? payload.updated_fields || [] : []
}

const complaintSlice = createSlice({
  name: 'complaint',
  initialState,
  reducers: {
    pushUserMessage(state, action) {
      state.messages.push({ role: 'user', content: action.payload })
    },
    clearHighlights(state) {
      state.recentlyUpdated = []
    },
    setProgress(state, action) {
      state.progress = action.payload
    },
    dismissError(state) {
      state.error = null
    },
  },
  extraReducers: (builder) => {
    builder
      // --- bootstrap ---
      .addCase(bootstrap.fulfilled, (state, action) => {
        applyServerState(state, action.payload, { recordUpdates: false })
        state.bootstrapped = true
        state.messages = [{ role: 'assistant', content: action.payload.assistant_message }]
      })
      .addCase(bootstrap.rejected, (state, action) => {
        state.error =
          'Could not reach the backend. Is it running on port 8000? ' +
          (action.error?.message || '')
      })

      // --- send message ---
      .addCase(sendMessage.pending, (state) => {
        state.isBusy = true
        state.phase = 'thinking'
        state.progress = 8
        state.error = null
      })
      .addCase(sendMessage.fulfilled, (state, action) => {
        applyServerState(state, action.payload)
        state.messages.push({
          role: 'assistant',
          content: action.payload.assistant_message,
          tool: action.payload.tool_used,
          trace: action.payload.trace,
        })
        state.isBusy = false
        state.phase = 'done'
        state.progress = 100
      })
      .addCase(sendMessage.rejected, (state, action) => {
        state.isBusy = false
        state.phase = 'idle'
        state.progress = 0
        state.error = action.payload || action.error?.message || 'Something went wrong'
        state.messages.push({
          role: 'assistant',
          content: `I could not process that. ${state.error}`,
          isError: true,
        })
      })

      // --- reset ---
      .addCase(resetComplaint.fulfilled, (state, action) => {
        applyServerState(state, action.payload, { recordUpdates: false })
        state.messages = [{ role: 'assistant', content: action.payload.assistant_message }]
        state.progress = 0
        state.phase = 'idle'
        state.summary = null
      })

      // --- save ---
      .addCase(saveComplaint.fulfilled, (state, action) => {
        applyServerState(state, action.payload, { recordUpdates: false })
        state.messages.push({ role: 'assistant', content: action.payload.assistant_message })
      })
      .addCase(saveComplaint.rejected, (state, action) => {
        state.error = action.payload || 'Could not save the complaint'
      })
  },
})

export const { pushUserMessage, clearHighlights, setProgress, dismissError } =
  complaintSlice.actions

export default complaintSlice.reducer

// --- Selectors ---
export const selectForm = (s) => s.complaint.form
export const selectRisk = (s) => s.complaint.risk
export const selectIsBusy = (s) => s.complaint.isBusy
export const selectHighlights = (s) => s.complaint.recentlyUpdated

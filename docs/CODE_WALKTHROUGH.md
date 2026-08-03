# Code Walkthrough

A single request traced through every layer, in the order the submission asks
for it: frontend input → frontend code → API endpoint → backend processing →
AI/LangGraph workflow → response populating the form and risk assessment.

This doubles as the script for the code-explanation video. Follow **one**
request all the way down rather than touring files — it's far more convincing
and it's what the brief asks for.

---

## The request we'll trace

> "sorry, the batch number is BMX24602 and the affected quantity is 48 capsules"

Chosen deliberately: it exercises the routing decision, the patch merge, the
preservation guarantee and the risk re-assessment in one turn. Log a complaint
first so there's something on file to amend.

---

## 1. Frontend input

`frontend/src/components/CopilotPanel.jsx` — the composer at the bottom.

```jsx
function submit() {
  const text = draft.trim()
  if (!text || isBusy) return
  dispatch(pushUserMessage(text))        // optimistic — user bubble appears now
  dispatch(sendMessage({ message: text }))
  setDraft('')
}
```

Two dispatches. The first paints the user's message immediately so the UI never
feels stalled. The second is the thunk that actually talks to the backend.

**Point out:** there is no `onChange` on any form field. Search the codebase
for it. The form is populated only by AI responses — that's the assignment's
core constraint, enforced structurally rather than by disabling inputs.

---

## 2. Redux thunk

`frontend/src/store/complaintSlice.js`

```js
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
```

`createAsyncThunk` gives three actions for free — `pending`, `fulfilled`,
`rejected` — which map onto the three UI states: spinner, result, error banner.

The `pending` reducer sets `isBusy` and starts the progress bar. The
`fulfilled` reducer is the important one:

```js
function applyServerState(state, payload, { recordUpdates = true } = {}) {
  state.form = { ...EMPTY_FORM, ...payload.form }
  state.risk = { ...EMPTY_RISK, ...payload.risk_assessment }
  state.recentlyUpdated = recordUpdates ? payload.updated_fields || [] : []
  // ...
}
```

**Point out:** the client never merges anything. It replaces `form` wholesale
with what the server sent. All merge logic lives in the graph, in one place,
covered by tests. If merging happened on both sides you'd have two
implementations to keep in sync and a race between them.

`recentlyUpdated` holds the field names that changed, which drives the blue
flash. That's what makes the demo legible — you can *see* that two fields
changed and eleven didn't.

---

## 3. API client

`frontend/src/api/client.js`

```js
sendMessage: (id, { message = '', file = null } = {}) => {
  const body = new FormData()
  body.append('message', message)
  if (file) body.append('file', file)
  return request(`/api/complaints/${id}/message`, { method: 'POST', body })
}
```

Always multipart, whether or not there's a file. One code path, one endpoint.

---

## 4. The endpoint

`backend/app/routers/complaints.py`

```python
@router.post("/{complaint_id}/message", response_model=ComplaintStateResponse)
async def send_message(complaint_id, message=Form(""), file=File(None), db=Depends(get_db)):
    row = repo.get_complaint(db, complaint_id)

    document_text = None
    if file is not None and file.filename:
        data = await file.read()
        document_text = extract_text(file.filename, data)

    state = repo.build_initial_state(row, message, document_text, document_name)

    result = get_graph().invoke(
        state, config={"configurable": {"thread_id": f"complaint-{complaint_id}"}}
    )

    return _to_response(row, result)
```

**Point out three things:**

**One endpoint for text and files.** From the graph's perspective they're the
same event — the user did something, run the workflow. Splitting into `/chat`
and `/upload` would push the routing decision into the frontend, where it
doesn't belong.

**State is rehydrated from Postgres every request.** `build_initial_state()`
reads the row and reconstructs the form. The database is the source of truth
between turns, so a refresh, a restart, or a second tab all see the same
complaint.

**`thread_id` is the complaint id.** That's how LangGraph's checkpointer keeps
per-complaint history isolated. Two complaints open in two tabs never see each
other's state.

---

## 5. The graph

`backend/app/graph/builder.py` — show the topology first. Either
`docs/graph.mmd`, or live:

```bash
curl localhost:8000/api/graph | jq -r .mermaid
```

Thirteen nodes. Then walk the path this request takes.

### 5a. Router — `nodes/router.py`

```python
def route_node(state):
    if state.get("has_document"):
        return {"intent": "extract_document", ...}   # deterministic short-circuit
```

**Point out:** if a file was uploaded there's nothing to classify, so we skip
the LLM entirely. Cheaper, faster, and it removes a failure mode where the
model reads the document text and misroutes.

For our text request it falls through to classification:

```python
state_line = ("NO COMPLAINT ON FILE — the form is completely empty"
              if not filled else "A COMPLAINT IS ALREADY ON FILE")
```

The prompt carries a bias rule: *if a complaint exists and the message supplies
facts rather than asking something, prefer `edit_complaint`* — because wrongly
choosing `log_complaint` destroys data the user already entered.

Then a safety net the model can't override:

```python
if intent == "extract_document":
    intent = "edit_complaint" if filled else "log_complaint"
```

The LLM cannot select a tool whose precondition isn't met. **Point out:** every
LLM decision in this system has a deterministic guard around it. The model
proposes; the code disposes.

→ routes to `edit_complaint`

### 5b. Edit tool — `nodes/tools.py`

**This is the heart of the walkthrough. Spend time here.**

The system prompt is unusually blunt because the failure mode is specific:

```
This is the most important rule in the system: DO NOT echo back fields the
user did not mention. If the user says "sorry, the batch number is BMX24602
and the affected quantity is 48 capsules", your entire response is:

    {"batch_lot_number": "BMX24602", "quantity_affected": "48 capsules"}

Nothing else. Every key you include overwrites stored data, so include the
minimum. Every key you omit is preserved automatically.
```

Then the merge, in `_apply_patch()`:

```python
def _apply_patch(state, patch, tool):
    current = state.get("form") or ComplaintForm()
    merged = current.merge(patch)

    before, after = current.model_dump(), merged.model_dump()
    changed = [k for k in after if before.get(k) != after.get(k)]
    return {"form": merged, "updated_fields": changed, ...}
```

And `ComplaintForm.merge()` in `schemas.py`:

```python
def merge(self, patch):
    merged = self.model_dump()
    merged.update(patch.model_dump(exclude_unset=True, exclude_none=True))
    return ComplaintForm.model_validate(merged)
```

**Say this out loud:** `exclude_unset=True` is the whole design. Every field on
`ComplaintForm` is `Optional` with no default, so a field the model didn't
mention isn't in the dict at all and cannot overwrite stored data with `None`.
`exclude_none=True` covers the case where a model emits an explicit `null`
anyway.

The alternative — asking the LLM to "return the updated form" — means it has to
correctly reproduce eleven fields it wasn't asked about, every single turn.
It will eventually drop some. Patching makes data loss structurally impossible
rather than something you prompt against and hope.

All three tools share `_apply_patch()`, so this guarantee is implemented once,
not three times.

→ `updated_fields = ["batch_lot_number", "quantity_affected"]`

### 5c. Risk assessment — `nodes/risk.py`

```python
if not state.get("updated_fields"):
    return {"trace": ["risk_assessment (skipped: no field changed)"]}
```

Skipped when nothing changed, so asking a question doesn't burn an LLM call.

Here it *did* change, so it re-runs against the **merged** form — all thirteen
fields, not just the two that moved. **Point out:** this is why it's a separate
node rather than extra keys on the extraction schema. If you correct the
affected quantity from 48 capsules to 75 kg across three drums, the severity
re-derives from the new total. Show that on camera; it's the most convincing
moment in the demo.

It also writes the assessed severity back onto the form, so the two panels stay
consistent:

```python
if assessment.severity_classification:
    updated_form = form.merge(ComplaintForm(initial_severity=...))
```

### 5d. Bonus chain — `nodes/bonus.py`

Three nodes, three different mechanisms:

- **`check_completeness`** — deterministic gap check against a mandatory-field
  list. One small LLM call only to phrase the follow-up naturally, so it reads
  "Could you confirm the manufacturing date?" instead of "Missing:
  manufacturing_date".
- **`duplicate_check`** — **no LLM at all.** Pure SQL against indexed columns
  plus token-overlap scoring. Duplicate detection over structured data is a
  database problem; doing it in SQL makes it exact, instant and free.
- **`generate_summary`** — two-sentence digest for a reviewer's worklist.

**Point out:** reaching for the LLM in all three would have been the easy
answer and the wrong one.

### 5e. Compose reply — `nodes/persist.py`

Deterministic string assembly, no LLM. **Point out:** this guarantees the chat
message can never contradict what actually changed. If you generated the
confirmation with an LLM it could cheerfully claim it updated a field it
didn't.

### 5f. Persist — `nodes/persist.py`

Writes the merged form to typed columns, the risk assessment to a JSON column,
and appends a revision:

```python
db.add(ComplaintRevision(
    complaint_id=complaint_id,
    tool_used=state.get("intent"),
    user_input=state.get("user_input"),
    patch=state.get("patch", {}),
    changed_fields=changed,
))
```

**Point out:** append-only, never updated, never deleted — even
`reset_complaint()` leaves revisions intact. A pharmaceutical QMS under 21 CFR
Part 11 needs an audit trail showing who changed what and when. Since every
mutation already flows through as a patch, capturing it gives the audit trail
almost for free.

Show it:

```bash
curl localhost:8000/api/complaints/1/audit | jq
```

---

## 6. Back up to the UI

The response carries the full state:

```json
{
  "form": { "batch_lot_number": "BMX24602", "quantity_affected": "48 capsules", ... },
  "risk_assessment": { "severity_classification": "Major", "risk_score": 6, ... },
  "updated_fields": ["batch_lot_number", "quantity_affected"],
  "trace": ["router → edit_complaint", "edit_complaint_tool (updated: ...)", ...]
}
```

Redux swaps it in, and `Field.jsx` reads it:

```jsx
const value = useSelector((s) => s.complaint.form[name])
const isHot = useSelector(selectHighlights).includes(name)
```

Two fields flash blue. Eleven don't. **That visual is the proof** — pause on it.

Finally, open the trace inspector under the assistant's message and show all
eight nodes that ran. It closes the loop: the thing you just walked through in
code is the thing that just executed.

---

## Interview prep

Questions they're likely to ask, given the brief says you may be asked to
extend the solution live.

**"How do you stop the LLM wiping the rest of the form?"**
The tools return patches, not forms. `exclude_unset=True` on
`model_dump()` means unmentioned fields aren't in the dict. Three tests in
`tests/test_graph.py` cover it.

**"Why LangGraph rather than three FastAPI endpoints?"**
Three things. Shared post-processing — the risk assessment runs after any
mutating tool without duplicating the call. Typed state that flows through
every node instead of being threaded through function arguments. And the
checkpointer gives per-complaint conversation history for free. Adding a fourth
tool is one node and one edge.

**"Why not use `gemma2-9b-it`?"**
Groq retired it — announced August 2025, pulled October 2025. Rather than
hard-coding a substitute I resolve models at startup against `GET /models` and
pick the highest-preference live one, logging the deviation. `gemma2-9b-it` is
still first in the extraction list, so it'd be used automatically if restored.
Details in `docs/MODEL_NOTES.md`.

**"What happens if the LLM returns malformed JSON?"**
JSON mode guarantees syntactic validity, not schema conformance. So `llm.py`
validates with Pydantic, and on failure sends the validation error back and
asks the model to repair its own output, up to two retries. If it still fails
it returns an empty schema instance — the graph degrades, the user loses that
turn's extraction, not their form data.

**"How would you add human-in-the-loop approval before saving?"**
`interrupt()` before the `persist` node, with a checkpointer that survives
process restart — swap `MemorySaver` for `PostgresSaver`. The graph pauses,
the API returns the pending state, and the user resumes with
`Command(resume=...)`. The state schema wouldn't change.

**"How would you scale this?"**
Extraction and reasoning are already split across two models. Next steps:
`duplicate_check` runs in parallel with `assess_risk` since neither depends on
the other; stream the graph with `.astream()` so the form paints field by
field; move to `PostgresSaver` so checkpoints survive restarts and you can run
multiple workers.

**"Where would this break in production?"**
Three places I'd fix first. Extraction accuracy on scanned PDFs — needs real
OCR, explicitly out of scope here. No authentication, so no user attribution on
audit revisions, which a real Part 11 system requires. And duplicate detection
uses token overlap; at scale it wants trigram similarity or embeddings.

**"Walk me through adding a new field to the form."**
Four places: the `ComplaintForm` schema, the SQLAlchemy column plus
`FORM_COLUMNS`, `EMPTY_FORM` in the Redux slice, and a `<Field>` in
`ComplaintForm.jsx`. No prompt changes needed — the JSON Schema is generated
from the Pydantic model and injected automatically, so the LLM learns the new
field for free. That's worth saying, it's a nice property of the design.

---

## Recording notes

**Reset first** so complaint numbers start at `CC-2026-0001`:

```bash
docker compose down -v && docker compose up -d db
```

**Order that builds best:**

1. Free-text prompt → form populates, risk appears *(log_complaint_tool)*
2. The correction → two fields flash, eleven don't *(edit_complaint_tool)* — pause here
3. Reset, upload the Metformin PDF → API complaint, different shape *(document_extraction_tool)*
4. Correct the batch on the extracted complaint → editing works post-extraction too
5. New complaint, upload the same PDF → duplicate warning fires
6. Ask "why did you classify this as Critical?" → Q&A branch, form untouched
7. `/api/health` → the model resolution story
8. `/api/complaints/1/audit` → the audit trail

**Have ready in browser tabs:** the app, `localhost:8000/docs`, and
`docs/graph.mmd` pasted into <https://mermaid.live> so the topology renders.

Steps 2 and 5 are the two moments that separate this from a form-filling demo.
Don't rush them.

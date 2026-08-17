# Agent Runtime API v2

v2 is the canonical, local-first Agent contract. It does not read or migrate v1 JSON Session/Run data. All timestamps are ISO-8601 UTC strings and all identifiers are opaque.

## Durable objects

- `AgentSession`: frozen Agent definition version, exact prefix text/hash, capability-index hash, model profile and active Run pointer.
- `AgentRun`: objective, FAST/STRUCTURED path, status, optimistic `revision`, pinned Skill/Tool versions, budgets and terminal result.
- `AgentEvent`: `event_id`, Session-scoped monotonic `sequence`, `event_type`, `payload`, `metadata`, `references`, and timestamp.
- `Checkpoint`: accumulated state plus lineage and the last covered event sequence.
- `ContextManifest`: the exact event range, Checkpoint, prefix/model/version pins, token breakdown and context hash used for one model turn.

The event stream is authoritative. Other records are projections or content referenced by events.

## Sessions and Runs

```text
GET    /api/v2/sessions
POST   /api/v2/sessions
GET    /api/v2/sessions/{session_id}
PATCH  /api/v2/sessions/{session_id}
DELETE /api/v2/sessions/{session_id}
GET    /api/v2/sessions/{session_id}/messages
DELETE /api/v2/sessions/{session_id}/messages/{event_id}?cascade=true

POST   /api/v2/sessions/{session_id}/runs
GET    /api/v2/runs/{run_id}
GET    /api/v2/runs/{run_id}/stream
POST   /api/v2/runs/{run_id}/approvals/{approval_id}
POST   /api/v2/runs/{run_id}/cancel
```

Create Run body:

```json
{
  "message": "分析本周延期风险",
  "source": "chat",
  "requested_skills": ["scheduling-query"],
  "artifact_ids": [],
  "principal_id": "local-user",
  "max_steps": 24,
  "max_seconds": 600
}
```

Only one main Run may be active in a Session. A conflict returns `409 session_busy`. Approval bodies contain `approved`, `expected_revision`, and `principal_id`; stale decisions return 409. Accepted decisions return 202 while execution resumes in the background.

## SSE

The stream is resumable with `Last-Event-ID`. Each frame uses the durable event id, uppercase canonical event type, and complete event JSON:

```text
id: 6ac…
event: TOOL_RESULT
data: {"event_id":"6ac…","sequence":12,"event_type":"TOOL_RESULT","payload":{…},…}
```

The server replays missed durable events, drains events published during replay, and closes when the Run is terminal or paused for approval/reconciliation. Clients reconnect after the pause is resolved and deduplicate by `event_id`.

## Debug and replay

```text
GET /api/v2/sessions/{session_id}/debug
GET /api/v2/runs/{run_id}/debug
GET /api/v2/sessions/{session_id}/replay
```

Debug responses expose trajectory, Plan/tasks, approvals, latest Checkpoint and ContextManifests. Replay verifies Session event-sequence continuity, frozen prefix hashes and Checkpoint coverage without calling a model or executing a capability.

## Local Knowledge and Memory

```text
GET    /api/v2/knowledge
POST   /api/v2/knowledge
DELETE /api/v2/knowledge/{document_id}
GET    /api/v2/memories
POST   /api/v2/memories
DELETE /api/v2/memories/{memory_id}
```

Mutations are host administration and require `Authorization: Bearer <PRIVILEGED_API_TOKEN>`. Model access is only through the read-only, bounded `knowledge_search` and `memory_search` Runtime capabilities.

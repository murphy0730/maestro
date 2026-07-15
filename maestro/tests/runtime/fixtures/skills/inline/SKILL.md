---
name: inspect-order
description: Inspect an order when the user asks for its current state.
allowed-tools: Read, Grep
argument-hint: <order-id>
user-invocable: true
disable-model-invocation: false
---
Inspect `$ARGUMENTS`. Use ${CLAUDE_SKILL_DIR} for relative resources and ${CLAUDE_SESSION_ID} for the run-scoped identifier.

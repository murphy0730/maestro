# Planning Rule MCP Tools Client Design

## Goal

Expose the planning server's two new tools through the existing generic MCP
client while preserving locally governed risk classification:

- `list_planning_rules` lists the 11 built-in rules, Chinese descriptions, and
  the default rule.
- `run_rule_planning` runs one real planning simulation for a selected rule and
  returns metrics, operation count, and at most 20 preview rows.

## Architecture

No planning-specific behavior is added to `maestro/runtime/`. The existing
stdio MCP client continues to discover both tools from `tools/list`, publish
them as `mcp__planning__*` capabilities, and forward calls through the Policy
Gate.

Local policy remains authoritative:

- Add `list_planning_rules` to the planning server's `read_only_tools`, making
  it `writes=false`, `risk=low`, and idempotent.
- Do not add `run_rule_planning` to `read_only_tools`. It updates the latest
  simulation result, so it remains `writes=true`, `risk=high`, and requires
  approval before execution.

The current host configuration in `~/.maestro/settings.json` will be updated
accordingly and the planning connector reconnected. No secret environment
values will be read back or logged.

## Client Test Fixture

Extend the deterministic planning MCP test server with the exact server-side
schemas:

- `list_planning_rules` accepts an empty object.
- `run_rule_planning` requires `rule_name`, restricted to the 11 built-in rule
  names.

Its structured test results will represent the real response shapes: rule
metadata for listing, and selected rule, metrics, operation count, bounded
preview, truncation flag, and latest-simulation update status for execution.

## Runtime Flow and Errors

Rule listing follows the normal fast-path MCP call and completes without an
approval. Rule execution first reaches `waiting_approval`; only an approved
call may reach the MCP server. Existing MCP handling remains unchanged:
`isError=true` becomes a failed capability result, while ordinary structured
business errors are returned to the model for correction or explanation.

## Verification

Tests will verify that:

1. both capabilities are discovered and visible to the model;
2. `list_planning_rules` runs without approval and returns structured rule data;
3. `run_rule_planning` is classified as a high-risk write and requests approval;
4. after approval, execution completes and returns the bounded structured
   planning result;
5. all existing planning MCP and generic Runtime invariant tests still pass.

The existing planning MCP implementation document will be updated from five to
seven tools and will explicitly distinguish the six trusted read-only tools
from the single side-effecting execution tool.

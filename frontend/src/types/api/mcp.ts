/** MCP server administration — mirrors `docs/api-contract/agent-runtime-v1.md` §MCP. */

export type McpStatus = 'connected' | 'disconnected' | 'error';

export interface McpToolSummary {
  name: string;
  /** Registry name the model sees: `mcp__{server}__{tool}`. */
  capability: string;
  description: string;
}

export interface McpServer {
  name: string;
  command: string;
  args: string[];
  /** Only key names come back — the backend never echoes secret values. */
  env_keys: string[];
  enabled: boolean;
  status: McpStatus;
  error: string;
  tools: McpToolSummary[];
}

export interface McpServerListResponse {
  servers: McpServer[];
}

export interface McpServerInput {
  name: string;
  command: string;
  args: string[];
  env: Record<string, string>;
  enabled: boolean;
}

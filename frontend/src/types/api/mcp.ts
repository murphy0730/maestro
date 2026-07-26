/** MCP server administration — mirrors `docs/api-contract/agent-runtime-v1.md` §MCP. */

export type McpStatus = 'connected' | 'disconnected' | 'error';

export interface McpToolSummary {
  name: string;
  /** Registry name the model sees: `mcp__{server}__{tool}`. */
  capability: string;
  description: string;
  read_only: boolean;
  writes: boolean;
  risk: 'low' | 'medium' | 'high';
}

export interface McpServer {
  name: string;
  command: string;
  args: string[];
  /** Only key names come back — the backend never echoes secret values. */
  env_keys: string[];
  enabled: boolean;
  read_only_tools: string[];
  status: McpStatus;
  error: string;
  tools: McpToolSummary[];
  /**
   * Not returned by the current backend — every configured server is editable.
   * Declared optional so the UI can already lock rows the host owns once
   * `GET /mcp/servers` starts reporting it; absent is read as "editable".
   */
  managed?: boolean;
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
  read_only_tools: string[];
}

import type { McpServer, McpServerInput, McpServerListResponse } from '@/types';
import { apiDelete, apiGet, apiPost, apiPut } from './client';

/** `GET /mcp/servers` — read-only; no privileged token needed. */
export function listMcpServers(): Promise<McpServerListResponse> {
  return apiGet<McpServerListResponse>('/mcp/servers');
}

/**
 * `PUT /mcp/servers/{name}` — create or update, then reconnect immediately.
 * Host administration: needs `VITE_PRIVILEGED_API_TOKEN`, else 403.
 */
export function upsertMcpServer(input: McpServerInput): Promise<McpServer> {
  return apiPut<McpServer>(`/mcp/servers/${encodeURIComponent(input.name)}`, input);
}

export function deleteMcpServer(name: string): Promise<void> {
  return apiDelete<void>(`/mcp/servers/${encodeURIComponent(name)}`);
}

export function reconnectMcpServer(name: string): Promise<McpServer> {
  return apiPost<McpServer>(`/mcp/servers/${encodeURIComponent(name)}/reconnect`, {});
}

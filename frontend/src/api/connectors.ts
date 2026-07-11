import type { ConnectorInput, ConnectorListResponse, ConnectorServer } from '@/types';
import { apiDelete, apiGet, apiPost } from './client';

export const listConnectors = () => apiGet<ConnectorListResponse>('/mcp/servers');
export const createConnector = (input: ConnectorInput) =>
  apiPost<ConnectorServer & { revision: number }>('/mcp/servers', input);
export const deleteConnector = (name: string, revision: number) =>
  apiDelete<{ deleted: boolean; revision: number }>(`/mcp/servers/${encodeURIComponent(name)}`, {
    body: { expected_revision: revision },
  });
export const connectConnector = (name: string, revision: number) =>
  apiPost<ConnectorServer & { revision: number }>(
    `/mcp/servers/${encodeURIComponent(name)}/connect`,
    { expected_revision: revision },
  );
export const disconnectConnector = (name: string, revision: number) =>
  apiPost<ConnectorServer & { revision: number }>(
    `/mcp/servers/${encodeURIComponent(name)}/disconnect`,
    { expected_revision: revision },
  );
export const testConnector = (input: ConnectorInput) =>
  apiPost<{
    ok: boolean;
    duration_ms: number;
    tools: { name: string; description: string }[];
    resources: unknown[];
    error?: string;
  }>('/mcp/servers/test', input);

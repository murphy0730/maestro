export interface ConnectorEnvValue { configured: boolean; secret: boolean; value: string | null }
export interface ConnectorServer {
  name: string; display_name?: string; description: string; transport_type: 'stdio';
  command?: string; args: string[]; env: Record<string, ConnectorEnvValue>;
  secret_env_keys: string[]; enabled: boolean; source: 'environment' | 'settings_file';
  managed: boolean; editable: boolean; status: 'disconnected' | 'connected' | 'error';
  tools_count: number; resources_count: number; error?: string;
}
export interface ConnectorListResponse { servers: ConnectorServer[]; revision: number }
export interface ConnectorInput {
  name: string; display_name?: string; description?: string; transport_type: 'stdio';
  command: string; args: string[]; env: Record<string, string>; secret_env_keys: string[];
  enabled?: boolean; expected_revision?: number;
}

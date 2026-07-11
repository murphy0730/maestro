export interface CatalogSource {
  id: string; kind: 'skill' | 'connector'; display_name: string; source_url: string;
  trust_tier: 'official' | 'verified';
}
export interface CatalogSkill {
  catalog_id: string; name: string; display_name: string; description: string;
  summary_zh?: string; description_zh?: string;
  author?: string; license?: string; version?: string; source_id: string; source_name: string;
  source_url: string; source_commit: string; package_sha256: string;
  compatibility_status: 'ready' | 'degraded' | 'not_ready'; warnings: string[];
  has_scripts: boolean; synced_at: string; last_checked_at: string; withdrawn: boolean;
  installable: boolean; install_block_reason?: string; installed: boolean;
  installed_sha256?: string; update_available: boolean;
}
export interface ConnectorEnvSpec { name: string; description: string; required: boolean; secret: boolean }
export interface CatalogConnector {
  catalog_id: string; name: string; display_name: string; description: string;
  summary_zh?: string;
  author?: string; license?: string; version?: string; source_id: string; source_name: string;
  source_url: string; source_commit: string; command: string; args: string[];
  env_schema: ConnectorEnvSpec[]; requirements: string[]; catalog_template_sha256: string;
  synced_at: string; last_checked_at: string; withdrawn: boolean; installable: boolean;
  install_block_reason?: string; configured: boolean; configured_name?: string; update_available: boolean;
}
export interface CatalogPage<T> { items: T[]; total: number; page: number; page_size: number }
export interface CatalogStatus { active: { run_id: string; status: string } | null; latest: { run_id: string; status: string; completed_at?: string; counts: Record<string, number>; errors: Record<string, string> } | null }

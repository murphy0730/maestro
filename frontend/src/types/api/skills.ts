export interface SkillMeta {
  name: string;
  display_name?: string;
  description: string;
  when_to_use?: string[];
  allowed_tools?: string[];
  user_invocable?: boolean;
  disable_model_invocation?: boolean;
  tool_preconditions?: Record<string, string[]>;
  version?: string;
  author?: string;
  license?: string;
  compatibility?: string;
  argument_hint?: string;
  extensions?: Record<string, unknown>;
  scripts?: string[];
  file_count: number;
  bytes: number;
  added_at: string;
  compatibility_status?: 'ready' | 'degraded' | 'not_ready' | 'disabled';
  warnings?: string[];
  package_sha256: string;
  trust?: SkillTrustStatus;
}

export interface SkillTrustStatus {
  level: 'untrusted' | 'user_trusted';
  valid: boolean;
  package_sha256: string;
  principal_id?: string;
  trusted_at?: string;
}

export interface SkillValidationReport {
  compatible: boolean;
  normalized_name?: string;
  compatibility_status: 'ready' | 'degraded' | 'not_ready' | 'disabled';
  capabilities: {
    prompt: boolean;
    attachments: boolean;
    scripts: boolean;
  };
  tool_mapping: Record<string, string>;
  normalized_frontmatter: Record<string, unknown>;
  warnings: string[];
  errors: string[];
}

export interface SkillListResponse {
  skills: SkillMeta[];
}

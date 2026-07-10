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
  file_count: number;
  bytes: number;
  added_at: string;
}

export interface SkillListResponse {
  skills: SkillMeta[];
}

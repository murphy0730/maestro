import type { SkillMeta } from '@/types';

export type SkillFilter = 'all' | 'ready' | 'attention' | 'script';

/**
 * 已安装技能的派生状态 —— 全部来自 `GET /skills` 的真实字段，
 * 不推断「有更新」这类当前后端无法回答的东西。
 */
export interface SkillStatus {
  hasScripts: boolean;
  trusted: boolean;
  /** 曾经信任过，但包内容变了，信任随之失效。 */
  staleTrust: boolean;
  compatible: boolean;
  /** 需要人处理：不兼容、带警告，或脚本包还没被信任。 */
  attention: boolean;
}

export function skillStatus(skill: SkillMeta): SkillStatus {
  const hasScripts = (skill.scripts?.length ?? 0) > 0;
  const level = skill.trust?.level === 'user_trusted';
  const trusted = level && skill.trust?.valid !== false;
  const compatible = (skill.compatibility_status ?? 'ready') === 'ready';
  return {
    hasScripts,
    trusted,
    staleTrust: level && skill.trust?.valid === false,
    compatible,
    attention:
      !compatible || (skill.warnings?.length ?? 0) > 0 || (hasScripts && !trusted),
  };
}

export function matchesSkillFilter(skill: SkillMeta, filter: SkillFilter): boolean {
  const status = skillStatus(skill);
  if (filter === 'ready') return !status.attention;
  if (filter === 'attention') return status.attention;
  if (filter === 'script') return status.hasScripts;
  return true;
}

export function skillMatchesQuery(skill: SkillMeta, query: string): boolean {
  if (!query) return true;
  return [skill.name, skill.display_name, skill.summary_zh, skill.description_zh, skill.description]
    .join(' ')
    .toLowerCase()
    .includes(query.toLowerCase());
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

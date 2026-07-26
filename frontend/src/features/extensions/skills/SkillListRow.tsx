import { Badge } from '@/components/ui/Badge';
import type { SkillMeta } from '@/types';
import { ExtensionIcon, dangerRowButton, rowButton } from '../shared';
import { skillStatus } from './skillStatus';

/** 技能信任态徽章：无脚本的包不需要信任，别用「未信任」吓人。 */
export function SkillTrustBadge({ skill }: { skill: SkillMeta }) {
  const status = skillStatus(skill);
  if (!status.hasScripts) return <Badge>纯提示词</Badge>;
  if (status.trusted) return <Badge tone="success">脚本已信任</Badge>;
  return <Badge tone="warning">{status.staleTrust ? '包已变更，信任失效' : '脚本未信任'}</Badge>;
}

export function SkillListRow({
  skill,
  busy,
  onOpen,
  onTrust,
  onDelete,
}: {
  skill: SkillMeta;
  busy: boolean;
  onOpen: () => void;
  onTrust: () => void;
  onDelete: () => void;
}) {
  const status = skillStatus(skill);
  const title = skill.display_name ?? skill.name;
  return (
    <div className="flex items-center gap-[14px] border-b border-border-subtle px-[10px] py-[12px] transition-colors duration-fast hover:bg-surface-3">
      <ExtensionIcon name={title} />
      <button
        type="button"
        onClick={onOpen}
        className="min-w-0 flex-1 text-left"
        aria-label={`查看技能 ${title} 详情`}
      >
        <span className="flex items-center gap-[8px] text-[13px] font-semibold text-text-primary">
          <span className="truncate">{title}</span>
          {skill.version && (
            <span className="flex-none font-mono text-[10.5px] font-normal text-text-tertiary">
              {skill.version}
            </span>
          )}
        </span>
        <span className="block truncate text-[11.5px] text-text-tertiary">
          {skill.summary_zh ?? skill.description}
        </span>
      </button>
      <span className="w-[110px] flex-none max-lg:hidden">
        <SkillTrustBadge skill={skill} />
      </span>
      <span className="w-[86px] flex-none max-lg:hidden">
        {status.compatible ? (
          <Badge tone="success">兼容</Badge>
        ) : (
          <Badge tone="warning">{skill.compatibility_status}</Badge>
        )}
      </span>
      <span className="flex flex-none items-center gap-[6px]">
        {status.hasScripts && !status.trusted && (
          <button type="button" disabled={busy} onClick={onTrust} className={rowButton}>
            信任
          </button>
        )}
        <button type="button" onClick={onOpen} className={rowButton}>
          详情
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onDelete}
          aria-label={`卸载技能 ${title}`}
          className={dangerRowButton}
        >
          卸载
        </button>
      </span>
    </div>
  );
}

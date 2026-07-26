import { CircleAlert, CircleCheck, FileText } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import type { SkillMeta } from '@/types';
import { DrawerKeyValues, DrawerSection, ExtensionDrawer } from '../ExtensionDrawer';
import { dangerButton, ghostButton } from '../shared';
import { SkillTrustBadge } from './SkillListRow';
import { formatBytes, skillStatus } from './skillStatus';

/**
 * 技能详情：只呈现 `GET /skills` 真实返回的字段。文件清单目前只有脚本文件名
 * 是已知的，所以列脚本 + 文件总数，不编造 references/ 里的条目。
 */
export function SkillDetailDrawer({
  skill,
  busy,
  onClose,
  onTrust,
  onRevokeTrust,
  onDelete,
}: {
  skill: SkillMeta;
  busy: boolean;
  onClose: () => void;
  onTrust: () => void;
  onRevokeTrust: () => void;
  onDelete: () => void;
}) {
  const status = skillStatus(skill);
  const title = skill.display_name ?? skill.name;

  return (
    <ExtensionDrawer
      open
      onClose={onClose}
      title={title}
      header={<SkillTrustBadge skill={skill} />}
      subtitle={`${skill.name}${skill.version ? ` · ${skill.version}` : ''}`}
      footer={
        <button type="button" onClick={onClose} className={`${ghostButton} ml-auto`}>
          关闭
        </button>
      }
    >
      <DrawerSection title="简介">
        <p className="m-0 text-[12.5px] leading-[1.7] text-text-secondary">
          {skill.description_zh ?? skill.description}
        </p>
      </DrawerSection>

      {skill.when_to_use?.length ? (
        <DrawerSection title="适用场景 · when_to_use">
          <ul className="m-0 list-disc pl-[18px] text-[12.5px] leading-[1.7] text-text-secondary">
            {skill.when_to_use.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </DrawerSection>
      ) : null}

      <DrawerSection title="能力摘要">
        <div className="flex flex-wrap gap-[6px]">
          <Badge tone="accent">Prompt</Badge>
          {skill.file_count > 1 && <Badge tone="accent">Resources</Badge>}
          {status.hasScripts ? (
            <Badge tone="warning">Scripts ×{skill.scripts?.length}</Badge>
          ) : (
            <Badge>无脚本</Badge>
          )}
          {skill.disable_model_invocation && <Badge tone="controlled">仅显式调用</Badge>}
        </div>
      </DrawerSection>

      {skill.allowed_tools?.length ? (
        <DrawerSection title="工具与权限 · allowed_tools">
          <div className="flex flex-wrap gap-[6px]">
            {skill.allowed_tools.map((tool) => (
              <Badge key={tool} tone="planning">
                {tool}
              </Badge>
            ))}
          </div>
          <p className="mt-[8px] text-[10.5px] leading-[1.6] text-text-tertiary">
            写类工具的每次调用仍由 Policy Gate 决定是否需要人工确认；信任脚本不等于免确认。
          </p>
        </DrawerSection>
      ) : null}

      {status.hasScripts && (
        <DrawerSection title="脚本文件">
          {skill.scripts?.map((script) => (
            <div
              key={script}
              className="flex items-center gap-[9px] border-b border-dashed border-border-subtle py-[6px] text-[12px] text-text-secondary last:border-b-0"
            >
              <FileText size={12} className="flex-none text-text-tertiary" />
              <span className="truncate font-mono text-[11px]">{script}</span>
            </div>
          ))}
        </DrawerSection>
      )}

      <DrawerSection title="兼容性">
        {status.compatible && !(skill.warnings?.length ?? 0) ? (
          <p className="m-0 flex items-start gap-[8px] text-[11.5px] leading-[1.6] text-status-success">
            <CircleCheck size={13} className="mt-[2px] flex-none" />
            通过本机预检：工具映射与 frontmatter 均兼容。
          </p>
        ) : (
          <>
            <p className="m-0 flex items-start gap-[8px] text-[11.5px] leading-[1.6] text-status-warning">
              <CircleAlert size={13} className="mt-[2px] flex-none" />
              兼容状态：{skill.compatibility_status ?? 'ready'}
            </p>
            {skill.warnings?.map((warning) => (
              <p
                key={warning}
                className="m-0 mt-[6px] pl-[21px] text-[11.5px] leading-[1.6] text-status-warning"
              >
                {warning}
              </p>
            ))}
          </>
        )}
      </DrawerSection>

      <DrawerSection title="包信息">
        <DrawerKeyValues
          rows={[
            ['SHA-256', skill.package_sha256],
            ['文件数', String(skill.file_count)],
            ['大小', formatBytes(skill.bytes)],
            ['安装时间', skill.added_at || '—'],
            ...(skill.author ? ([['作者', skill.author]] as Array<[string, string]>) : []),
            ...(skill.license ? ([['许可', skill.license]] as Array<[string, string]>) : []),
          ]}
        />
      </DrawerSection>

      <DrawerSection title="危险操作">
        <div className="flex flex-col gap-[8px] rounded-lg border border-status-error/30 p-[14px]">
          {status.hasScripts && (
            <div className="flex items-center gap-[10px]">
              <div className="min-w-0 flex-1">
                <b className="block text-[12.5px] font-medium text-text-primary">
                  {status.trusted ? '取消信任' : '信任当前包'}
                </b>
                <span className="text-[11px] leading-[1.6] text-text-tertiary">
                  信任绑定当前包 Hash，包一变就自动失效；脚本执行仍需人工审批。
                </span>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={status.trusted ? onRevokeTrust : onTrust}
                className={`${ghostButton} flex-none`}
              >
                {status.trusted ? '取消信任' : '信任'}
              </button>
            </div>
          )}
          <div className="flex items-center gap-[10px]">
            <div className="min-w-0 flex-1">
              <b className="block text-[12.5px] font-medium text-text-primary">卸载技能</b>
              <span className="text-[11px] leading-[1.6] text-text-tertiary">
                删除本地包文件与注册信息，不影响历史会话记录。
              </span>
            </div>
            <button
              type="button"
              disabled={busy}
              onClick={onDelete}
              className={`${dangerButton} flex-none`}
            >
              卸载技能
            </button>
          </div>
        </div>
      </DrawerSection>
    </ExtensionDrawer>
  );
}

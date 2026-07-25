import { useMemo, useState } from 'react';
import { Plus, Search, ShieldCheck, ShieldX, Trash2 } from 'lucide-react';
import { deleteSkill, revokeSkillTrust, trustSkill } from '@/api';
import { Modal } from '@/components/ui/Modal';
import { Badge } from '@/components/ui/Badge';
import type { SkillMeta } from '@/types';

/**
 * SkillManagerModal — 设计稿 G：技能卡片墙 + 虚线导入卡。
 * 信任态、脚本数等只用 /skills 返回的真实字段；未信任卡挂 HUD 角括号提示需要处理。
 */
export function SkillManagerModal({ open, onClose, skills, loading, onImport, onChanged }: { open: boolean; onClose: () => void; skills: SkillMeta[]; loading: boolean; onImport: () => void; onChanged: () => void }) {
  const [query, setQuery] = useState('');
  const [pending, setPending] = useState<string>();
  const [error, setError] = useState<string>();
  const [trust, setTrust] = useState<Record<string, boolean>>({});
  const filtered = useMemo(
    () => skills.filter((skill) => `${skill.name} ${skill.display_name ?? ''} ${skill.description}`.toLowerCase().includes(query.toLowerCase())),
    [skills, query],
  );
  const mutate = async (key: string, action: () => Promise<unknown>, after?: () => void) => {
    setPending(key);
    setError(undefined);
    try {
      await action();
      after?.();
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '操作失败');
    } finally {
      setPending(undefined);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="技能 · 连接器管理" subtitle="所有数据来自当前 Runtime /skills 接口" widthClassName="max-w-[760px]" bodyClassName="p-[18px]">
      <label className="mb-[16px] flex items-center gap-[8px] rounded-md border border-border-subtle bg-surface-2 px-[12px] py-[7px] text-text-tertiary transition-colors focus-within:border-accent">
        <Search size={14} className="flex-none" />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索技能…" className="min-w-0 flex-1 bg-transparent text-body-sm text-text-primary outline-none placeholder:text-text-tertiary" />
      </label>

      {error && <p role="alert" className="mb-[12px] rounded-md bg-status-error-bg p-[12px] text-caption text-status-error">{error}</p>}

      <div className="grid grid-cols-2 gap-[12px] max-sm:grid-cols-1">
        {filtered.map((skill) => {
          const trusted = trust[skill.name] ?? skill.trust?.valid ?? false;
          const busy = pending === skill.name;
          return (
            <article
              key={skill.name}
              className={`group relative rounded-lg border border-border-subtle bg-surface-2 p-[14px] transition duration-normal ease-out hover:border-border-strong hover:shadow-elev-2 ${trusted ? '' : 'hud-brackets'}`}
            >
              <h3 className="m-0 mb-[4px] truncate text-[13.5px] font-medium text-text-primary">{skill.display_name ?? skill.name}</h3>
              <p className="mb-[10px] line-clamp-3 min-h-[36px] text-[11.5px] leading-[1.55] text-text-secondary">{skill.description}</p>
              <div className="flex flex-wrap items-center gap-[8px]">
                {skill.scripts && skill.scripts.length > 0 && <Badge tone="planning">Scripts ×{skill.scripts.length}</Badge>}
                <Badge tone={trusted ? 'success' : 'warning'}>{trusted ? '已信任' : '未信任'}</Badge>
                {trusted ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void mutate(skill.name, () => revokeSkillTrust(skill.name), () => setTrust((current) => ({ ...current, [skill.name]: false })))}
                    className="inline-flex items-center gap-[4px] rounded-sm border border-border-strong px-[10px] py-[3px] text-[11px] text-text-secondary transition-colors hover:border-status-error hover:text-status-error disabled:opacity-50"
                  >
                    <ShieldX size={12} />撤销信任
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void mutate(skill.name, () => trustSkill(skill.name, true), () => setTrust((current) => ({ ...current, [skill.name]: true })))}
                    className="inline-flex items-center gap-[4px] rounded-sm border border-border-strong px-[10px] py-[3px] text-[11px] text-text-primary transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
                  >
                    <ShieldCheck size={12} />信任
                  </button>
                )}
                <span className="flex-1" />
                <button
                  type="button"
                  disabled={busy}
                  aria-label={`删除技能 ${skill.name}`}
                  title="删除已导入技能"
                  onClick={() => {
                    if (window.confirm(`仅删除已导入技能“${skill.name}”？`)) void mutate(skill.name, () => deleteSkill(skill.name));
                  }}
                  className="grid h-[24px] w-[24px] flex-none place-items-center rounded-sm text-text-tertiary opacity-0 transition-opacity duration-fast hover:bg-status-error-bg hover:text-status-error focus-visible:opacity-100 group-hover:opacity-100 disabled:opacity-50"
                >
                  <Trash2 size={13} />
                </button>
              </div>
              <div className="mt-[8px] font-mono text-[9px] uppercase tracking-[0.12em] text-text-tertiary">
                Files {skill.file_count} · {skill.bytes} B · {skill.compatibility_status ?? 'ready'}
              </div>
            </article>
          );
        })}

        <button
          type="button"
          onClick={onImport}
          className="grid min-h-[118px] place-items-center rounded-lg border border-dashed border-border-strong text-caption text-text-tertiary transition-colors duration-normal ease-out hover:border-accent hover:text-accent"
        >
          <span className="inline-flex items-center gap-[8px]"><Plus size={14} />导入技能（.md / .zip）</span>
        </button>
      </div>

      {!loading && filtered.length === 0 && <p className="py-[40px] text-center text-caption text-text-tertiary">没有匹配的技能</p>}
      {loading && <p role="status" className="py-[40px] text-center text-caption text-text-tertiary">正在加载技能…</p>}
      <p className="mt-[16px] text-caption text-text-tertiary">注：当前 GET /skills 未返回进程信任状态；本面板只展示本次操作得到的真实响应，不伪造重启后的状态。</p>
    </Modal>
  );
}

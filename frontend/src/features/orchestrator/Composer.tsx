import { useState } from 'react';
import { ShieldCheck, Sparkles, X, Zap } from 'lucide-react';
import type { ComposerMode, ComposerRoute, SkillMeta } from '@/types';
import { ComposerToolbar } from './ComposerToolbar';

interface ComposerProps {
  onSend: (text: string) => void;
  route: ComposerRoute;
  mode: ComposerMode;
  onRouteChange: (route: ComposerRoute) => void;
  onModeChange: (mode: ComposerMode) => void;
  isStreaming?: boolean;
  onStop?: () => void;
  skills: SkillMeta[];
  selectedSkills: SkillMeta[];
  onToggleSkill: (skill: SkillMeta) => void;
  onClearSkills: () => void;
  onImportSkill: () => void;
  onTrustSkill?: (skill: SkillMeta) => void;
}

const ROUTE_LABELS: Record<ComposerRoute, string> = {
  auto: '自动',
  planning: '排产',
  scheduling: '调度',
  query: '查询',
};

export function Composer({
  onSend,
  route,
  mode,
  onRouteChange,
  onModeChange,
  isStreaming = false,
  onStop,
  skills,
  selectedSkills,
  onToggleSkill,
  onClearSkills,
  onImportSkill,
  onTrustSkill,
}: ComposerProps) {
  const [draft, setDraft] = useState('');
  const slash = draft.startsWith('/');
  const routeLabel = ROUTE_LABELS[route];

  const submit = () => {
    if (isStreaming) return;
    const text = draft.trim();
    if (!text) return;
    onSend(text);
    setDraft('');
  };

  return (
    <div className="flex-none px-[30px] pb-[18px] pt-2">
      <div className="pointer-events-auto mx-auto max-w-[760px]">
        <div
          className={`material-dock rounded-lg border transition-colors duration-fast ${
            slash
              ? 'border-accent-border shadow-glow-accent'
              : 'border-border-default shadow-elev-2'
          }`}
        >
          {selectedSkills.length > 0 && (
            <div className="flex flex-wrap items-center gap-[6px] px-[12px] pt-[10px]">
              {selectedSkills.map((skill) => (
                <span
                  key={skill.name}
                  className="inline-flex h-[26px] items-center gap-[6px] rounded-md border border-accent-border bg-accent-bg px-[8px] text-caption font-medium text-text-primary"
                >
                  <Sparkles size={12} className="text-accent" />
                  {skill.display_name ?? skill.name}
                  <button
                    type="button"
                    title="移除技能"
                    onClick={() => onToggleSkill(skill)}
                    className="grid h-[16px] w-[16px] place-items-center rounded-sm text-text-tertiary hover:bg-border-subtle hover:text-text-secondary"
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          )}
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            rows={1}
            placeholder="描述排产 / 调度 / 查询需求，输入 / 调用斜杠命令，或粘贴工单号 WO-…"
            className="block max-h-[120px] w-full resize-none border-none bg-transparent px-[15px] pb-[7px] pt-[13px] font-sans text-body leading-normal text-text-primary outline-none placeholder:text-text-tertiary"
          />
          <ComposerToolbar
            isStreaming={isStreaming}
            mode={mode}
            onClearSkills={onClearSkills}
            onImportSkill={onImportSkill}
            onTrustSkill={onTrustSkill}
            onModeChange={onModeChange}
            onRouteChange={onRouteChange}
            onStop={onStop}
            onSubmit={submit}
            onToggleSkill={onToggleSkill}
            route={route}
            selectedSkills={selectedSkills}
            skills={skills}
          />
        </div>
        <div className="mt-2 flex items-center gap-[7px] text-[11px] text-text-tertiary">
          {mode === 'auto' ? (
            <Zap size={12} className="text-auth-confirm" />
          ) : (
            <ShieldCheck size={12} className="text-text-tertiary" />
          )}
          <span>
            {route === 'auto' ? '引擎自动分类' : `指定 ${routeLabel}引擎`} ·{' '}
            {mode === 'auto'
              ? '完全访问模式：Agent 可直接写入 MES'
              : '默认模式：写操作需确认后执行'}
          </span>
          <span className="flex-1" />
          <span className="font-mono">Enter 发送 · Shift+Enter 换行</span>
        </div>
      </div>
    </div>
  );
}

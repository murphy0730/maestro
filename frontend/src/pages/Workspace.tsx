import { useEffect, useState } from 'react';
import { Layout } from '@/components/layout/Layout';
import { TopBar } from '@/components/layout/TopBar';
import { Composer } from '@/features/orchestrator/Composer';
import { RunTrace } from '@/features/runtime/RunTrace';
import { Markdown } from '@/components/ui/Markdown';
import { useSkills } from '@/api';
import { useRunStream } from '@/api/useRunStream';
import { useRunStore } from '@/stores/runStore';
import type { SkillMeta } from '@/types';

export function Workspace() {
  const [clock, setClock] = useState('--:--:--'); const [expert, setExpert] = useState(false); const [skills, setSkills] = useState<SkillMeta[]>([]); const [approvingId, setApprovingId] = useState<string | null>(null);
  const skillsQuery = useSkills(); const projection = useRunStore((state) => ({ run: state.run, tokens: state.tokens, upgradeReason: state.upgradeReason, diagnostics: state.diagnostics }));
  const { start, approve, cancel, transport } = useRunStream('default');
  useEffect(() => { const tick = () => setClock(new Date().toLocaleTimeString('en-GB')); tick(); const id = window.setInterval(tick, 1000); return () => window.clearInterval(id); }, []);
  const availableSkills = skillsQuery.data?.skills ?? [];
  return <Layout topBar={<TopBar session={projection.run?.objective || '新任务'} clock={clock} />} conversation={<main className="flex min-h-0 flex-1"><section className="flex min-w-0 flex-1 flex-col"><div className="min-h-0 flex-1 overflow-y-auto px-[30px] py-6"><div className="mx-auto max-w-[760px] space-y-5">{!projection.run && <div className="pt-24 text-center"><h1 className="m-0 text-h2 font-semibold text-text-primary">制造执行 Agent</h1><p className="mt-2 text-body text-text-secondary">描述目标，Agent 将按 Skill、工具与权限策略推进任务。</p></div>}{projection.run && <><div className="rounded-md border border-border-subtle bg-surface-1 p-4 text-body text-text-primary">{projection.run.objective}</div>{projection.tokens && <div className="text-body leading-relaxed text-text-primary"><Markdown>{projection.tokens}</Markdown></div>}{projection.run.final_text && projection.run.final_text !== projection.tokens && <div className="text-body leading-relaxed text-text-primary"><Markdown>{projection.run.final_text}</Markdown></div>}{projection.upgradeReason && <p className="text-caption text-text-secondary">已因 {projection.upgradeReason} 升级为受控执行。</p>}</>}</div></div><Composer onSend={(message, files) => { void start(message, files, skills.map((skill) => skill.name), expert); }} expert={expert} onExpertChange={setExpert} disabled={transport === 'connecting'} isStreaming={transport === 'connecting' || transport === 'streaming'} onStop={() => { void cancel(); }} skills={availableSkills} selectedSkills={skills} onToggleSkill={(skill) => setSkills((current) => current.some((item) => item.name === skill.name) ? current.filter((item) => item.name !== skill.name) : [...current, skill])} onClearSkills={() => setSkills([])} onImportSkill={() => undefined} /></section><RunTrace projection={projection} approvingId={approvingId} onApprove={(approval, approved) => { setApprovingId(approval.approval_id); void approve(approval.approval_id, approved, approval.run_revision).finally(() => setApprovingId(null)); }} /></main>} />;
}

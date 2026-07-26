import { useRef } from 'react';
import { CircleAlert, Upload } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import type { SkillMeta } from '@/types';
import { DrawerKeyValues, ExtensionDrawer } from '../ExtensionDrawer';
import { ghostButton, primaryButton } from '../shared';
import { useSkillPackageImport } from './useSkillPackageImport';

/**
 * 导入抽屉：选包 → 预检 → 人看过警告后确认落盘。
 * 预检未通过不给确认入口；有警告时确认按钮仍需一次显式点击。
 */
export function SkillImportDrawer({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: (skill: SkillMeta) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const importer = useSkillPackageImport((skill) => {
    onImported(skill);
    onClose();
  });
  const { report } = importer;

  return (
    <ExtensionDrawer
      open
      onClose={importer.importing ? () => undefined : onClose}
      title="导入技能"
      subtitle="支持 .md / .zip，≤ 10 MB"
      footer={
        <>
          <button
            type="button"
            disabled={!importer.canConfirm}
            onClick={() => {
              void importer.confirm();
            }}
            className={`${primaryButton} flex-1 justify-center`}
          >
            {importer.importing ? '正在导入…' : '确认导入'}
          </button>
          <button
            type="button"
            disabled={importer.importing}
            onClick={onClose}
            className={ghostButton}
          >
            取消
          </button>
        </>
      }
    >
      <input
        ref={input}
        type="file"
        accept=".md,.zip"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = '';
          if (file) void importer.choose(file);
        }}
      />
      <button
        type="button"
        disabled={importer.validating || importer.importing}
        onClick={() => input.current?.click()}
        className="w-full rounded-lg border border-dashed border-border-strong p-[26px] text-center text-[12.5px] text-text-tertiary transition-colors duration-fast hover:border-accent hover:bg-accent-bg hover:text-accent disabled:opacity-50"
      >
        <Upload size={26} className="mx-auto mb-[8px]" />
        {importer.file ? importer.file.name : '点击选择技能包（.md / .zip）'}
        <span className="mt-[6px] block text-[10.5px] text-text-tertiary">
          与未来的远程 SkillHub 包共用同一套 validate 预检
        </span>
      </button>

      <div aria-live="polite" className="mt-[14px]">
        {importer.validating && (
          <p className="m-0 text-[12px] text-text-tertiary">正在预检技能包…</p>
        )}

        {importer.importing && (
          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(importer.progress * 100)}
            className="h-[6px] overflow-hidden rounded-pill bg-surface-3"
          >
            <span
              className="block h-full bg-accent transition-[width]"
              style={{ width: `${Math.max(8, importer.progress * 100)}%` }}
            />
          </div>
        )}

        {report && (
          <div className="overflow-hidden rounded-lg border border-border-subtle">
            <div className="flex items-center gap-[8px] border-b border-border-subtle bg-surface-2 px-[14px] py-[10px] text-[12.5px] font-semibold text-text-primary">
              <span className="truncate">{importer.file?.name}</span>
              <span className="ml-auto flex-none">
                {report.compatible ? (
                  <Badge tone="success">预检通过</Badge>
                ) : (
                  <Badge tone="danger">预检未通过</Badge>
                )}
              </span>
            </div>
            <div className="px-[14px] py-[12px]">
              <DrawerKeyValues
                rows={[
                  ['技能名', report.normalized_name ?? '—'],
                  ['兼容状态', report.compatibility_status],
                  [
                    '能力',
                    [
                      report.capabilities.prompt && 'Prompt',
                      report.capabilities.attachments && 'Resources',
                      report.capabilities.scripts && 'Scripts',
                    ]
                      .filter(Boolean)
                      .join(' + ') || '—',
                  ],
                  [
                    '工具映射',
                    Object.entries(report.tool_mapping)
                      .map(([from, to]) => `${from} → ${to}`)
                      .join('，') || '—',
                  ],
                ]}
              />
              {report.errors.map((message) => (
                <p
                  key={message}
                  className="m-0 mt-[8px] flex items-start gap-[8px] text-[11.5px] leading-[1.6] text-status-error"
                >
                  <CircleAlert size={13} className="mt-[2px] flex-none" />
                  {message}
                </p>
              ))}
              {report.warnings.map((message) => (
                <p
                  key={message}
                  className="m-0 mt-[8px] flex items-start gap-[8px] text-[11.5px] leading-[1.6] text-status-warning"
                >
                  <CircleAlert size={13} className="mt-[2px] flex-none" />
                  {message}
                </p>
              ))}
              {report.capabilities.scripts && (
                <p className="m-0 mt-[8px] text-[11px] leading-[1.6] text-text-tertiary">
                  包内含脚本：导入后需在详情页显式信任，且每次执行仍需人工审批。
                </p>
              )}
            </div>
          </div>
        )}

        {importer.error && (
          <p
            role="alert"
            className="m-0 mt-[12px] rounded-md bg-status-error-bg p-[12px] text-[12px] text-status-error"
          >
            {importer.error}
          </p>
        )}
      </div>
    </ExtensionDrawer>
  );
}

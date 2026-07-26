import { useCallback, useState } from 'react';
import { importSkill, useInvalidateSkills, validateSkill } from '@/api';
import type { SkillMeta, SkillValidationReport } from '@/types';
import { errorMessage } from '../errors';

/**
 * 两段式导入：先 `POST /skills/validate` 预检，把警告摆到人眼前，
 * 再由使用者显式确认后才 `POST /skills/import` 落盘。
 * 预检未通过的包不提供确认入口。
 */
export function useSkillPackageImport(onImported?: (skill: SkillMeta) => void) {
  const invalidateSkills = useInvalidateSkills();
  const [file, setFile] = useState<File>();
  const [report, setReport] = useState<SkillValidationReport>();
  const [validating, setValidating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string>();

  const reset = useCallback(() => {
    setFile(undefined);
    setReport(undefined);
    setError(undefined);
    setProgress(0);
  }, []);

  const choose = useCallback(async (picked: File) => {
    setReport(undefined);
    setError(undefined);
    setProgress(0);
    setFile(picked);
    if (!/\.(md|zip)$/i.test(picked.name)) {
      setError('仅支持 .md 或 .zip Skill 包');
      return;
    }
    if (picked.size > 10 * 1024 * 1024) {
      setError('Skill 包不能超过 10 MB');
      return;
    }
    setValidating(true);
    try {
      setReport(await validateSkill(picked));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setValidating(false);
    }
  }, []);

  const confirm = useCallback(async () => {
    if (!file || !report?.compatible) return;
    setImporting(true);
    setError(undefined);
    try {
      const imported = await importSkill(file, setProgress);
      await invalidateSkills();
      onImported?.(imported);
      reset();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setImporting(false);
    }
  }, [file, invalidateSkills, onImported, report, reset]);

  return {
    file,
    report,
    validating,
    importing,
    progress,
    error,
    choose,
    confirm,
    reset,
    canConfirm: Boolean(file && report?.compatible && !validating && !importing),
  };
}

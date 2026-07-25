import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

const mocks = vi.hoisted(() => ({ validateSkill: vi.fn(), importSkill: vi.fn() }));
vi.mock('@/api', () => mocks);
import { SkillImportModal } from './SkillImportModal';

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('SkillImportModal', () => {
  it('rejects unsupported file types before calling the API', () => {
    render(<SkillImportModal open onClose={vi.fn()} onImported={vi.fn()} />);
    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [new File(['x'], 'skill.txt')] } });
    expect(screen.getByRole('alert').textContent).toContain('.md 或 .zip');
    expect(mocks.validateSkill).not.toHaveBeenCalled();
  });

  it('shows structured validation errors and does not import', async () => {
    mocks.validateSkill.mockResolvedValue({ compatible: false, compatibility_status: 'not_ready', capabilities: { prompt: true, attachments: false, scripts: false }, tool_mapping: {}, normalized_frontmatter: {}, warnings: [], errors: ['allowed-tools 未注册'] });
    render(<SkillImportModal open onClose={vi.fn()} onImported={vi.fn()} />);
    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [new File(['x'], 'SKILL.md')] } });
    expect((await screen.findByRole('alert')).textContent).toContain('allowed-tools 未注册');
    expect(mocks.importSkill).not.toHaveBeenCalled();
  });

  it('validates before import and reports the imported skill', async () => {
    mocks.validateSkill.mockResolvedValue({ compatible: true, normalized_name: 'quality', compatibility_status: 'ready', capabilities: { prompt: true, attachments: false, scripts: false }, tool_mapping: {}, normalized_frontmatter: {}, warnings: [], errors: [] });
    const imported = { name: 'quality', description: '质量分析', file_count: 1, bytes: 1, added_at: '', package_sha256: 'sha' };
    mocks.importSkill.mockImplementation(async (_file: File, onProgress?: (value: number) => void) => { onProgress?.(1); return imported; });
    const onImported = vi.fn();
    const onClose = vi.fn();
    render(<SkillImportModal open onClose={onClose} onImported={onImported} />);
    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [new File(['x'], 'SKILL.md')] } });
    await vi.waitFor(() => expect(onImported).toHaveBeenCalledWith(imported));
    expect(mocks.validateSkill.mock.invocationCallOrder[0]).toBeLessThan(mocks.importSkill.mock.invocationCallOrder[0]);
    expect(onClose).toHaveBeenCalled();
  });
});

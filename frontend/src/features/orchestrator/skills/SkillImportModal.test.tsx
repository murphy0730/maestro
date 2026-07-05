import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { SkillImportModal } from './SkillImportModal';

vi.mock('@/api', () => ({
  useImportSkill: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false, error: null })),
}));
import { useImportSkill } from '@/api';

afterEach(cleanup);

describe('SkillImportModal', () => {
  it('renders drop zone and accepts a file', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ name: 'cap' });
    (useImportSkill as any).mockReturnValue({
      mutateAsync,
      isPending: false,
      error: null,
    });
    render(<SkillImportModal open onClose={() => {}} onImported={() => {}} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'cap.md')] } });
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  });

  it('shows error message on failure', () => {
    (useImportSkill as any).mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: { message: 'skill name 重复' },
    });
    render(<SkillImportModal open onClose={() => {}} onImported={() => {}} />);
    expect(screen.getByText(/技能包不符合规范/)).toBeTruthy();
  });
});

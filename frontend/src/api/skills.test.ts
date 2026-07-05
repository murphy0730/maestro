import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./client', () => ({
  apiGet: vi.fn(),
  apiUpload: vi.fn(),
  apiDelete: vi.fn(),
}));

import { apiGet, apiUpload, apiDelete } from './client';
import { listSkills, importSkill, deleteSkill } from './skills';

describe('skills api', () => {
  beforeEach(() => vi.clearAllMocks());

  it('listSkills calls GET /skills', async () => {
    vi.mocked(apiGet).mockResolvedValue({ skills: [] });
    await listSkills();
    expect(apiGet).toHaveBeenCalledWith('/skills');
  });

  it('importSkill posts file to /skills/import', async () => {
    vi.mocked(apiUpload).mockResolvedValue({
      name: 'cap',
      description: '',
      file_count: 1,
      bytes: 1,
      added_at: '',
    });
    await importSkill(new File(['x'], 'cap.md'));
    expect(apiUpload).toHaveBeenCalledWith(
      '/skills/import',
      expect.any(FormData),
      'POST',
      expect.anything(),
    );
  });

  it('deleteSkill calls DELETE /skills/:name', async () => {
    vi.mocked(apiDelete).mockResolvedValue(undefined);
    await deleteSkill('cap');
    expect(apiDelete).toHaveBeenCalledWith('/skills/cap');
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiUpload: vi.fn(),
  apiDelete: vi.fn(),
}));

import { apiGet, apiPost, apiUpload, apiDelete } from './client';
import { listSkills, importSkill, validateSkill, trustSkill, deleteSkill } from './skills';

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
      package_sha256: 'hash',
    });
    await importSkill(new File(['x'], 'cap.md'));
    expect(apiUpload).toHaveBeenCalledWith(
      '/skills/import',
      expect.any(FormData),
      'POST',
      expect.anything(),
    );
  });

  it('trustSkill uses the v1 trust contract', async () => {
    vi.mocked(apiPost).mockResolvedValue({ level: 'user_trusted', valid: true });
    await trustSkill('cap', true);
    expect(apiPost).toHaveBeenCalledWith('/skills/cap/trust', {
      trusted: true,
    });
  });

  it('validateSkill posts file to /skills/validate', async () => {
    vi.mocked(apiUpload).mockResolvedValue({ compatible: true });
    const file = new File(['x'], 'cap.md');
    await validateSkill(file);
    expect(apiUpload).toHaveBeenCalledWith('/skills/validate', expect.any(FormData));
  });

  it('deleteSkill calls DELETE /skills/:name', async () => {
    vi.mocked(apiDelete).mockResolvedValue(undefined);
    await deleteSkill('cap');
    expect(apiDelete).toHaveBeenCalledWith('/skills/cap');
  });
});

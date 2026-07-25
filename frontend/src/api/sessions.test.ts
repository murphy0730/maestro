import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
}));

import { apiDelete, apiPatch } from './client';
import { deleteSession, renameSession } from './sessions';

describe('session mutations', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renames through PATCH /sessions/:id', async () => {
    vi.mocked(apiPatch).mockResolvedValue({ session_id: 's1', title: '新标题' });
    await renameSession('s1', '新标题');
    expect(apiPatch).toHaveBeenCalledWith('/sessions/s1', { title: '新标题' });
  });

  it('deletes through DELETE /sessions/:id', async () => {
    vi.mocked(apiDelete).mockResolvedValue({ deleted: true, session_id: 's1' });
    await deleteSession('s1');
    expect(apiDelete).toHaveBeenCalledWith('/sessions/s1');
  });
});

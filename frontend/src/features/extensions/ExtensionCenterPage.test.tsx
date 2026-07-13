import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CatalogConnector, CatalogSkill, SkillMeta } from '@/types';
import { ExtensionCenterPage } from './ExtensionCenterPage';

const installCatalogSkill = vi.fn();
const addCatalogConnector = vi.fn();
const listCatalogSkills = vi.fn();
const listCatalogConnectors = vi.fn();
const useSkills = vi.fn();
const trustSkill = vi.fn();

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ conversation }: { conversation: React.ReactNode }) => <>{conversation}</>,
}));
vi.mock('@/features/orchestrator/skills/SkillImportModal', () => ({
  SkillImportModal: () => null,
}));
vi.mock('@/api', () => ({
  addCatalogConnector: (...args: unknown[]) => addCatalogConnector(...args),
  connectConnector: vi.fn(),
  createConnector: vi.fn(),
  deleteConnector: vi.fn(),
  disconnectConnector: vi.fn(),
  getCatalogStatus: vi.fn().mockResolvedValue({ active: null, latest: null }),
  installCatalogSkill: (...args: unknown[]) => installCatalogSkill(...args),
  listCatalogConnectors: (...args: unknown[]) => listCatalogConnectors(...args),
  listCatalogSkills: (...args: unknown[]) => listCatalogSkills(...args),
  listConnectors: vi.fn().mockResolvedValue({ servers: [], revision: 7 }),
  previewCatalogConnectorUpdate: vi.fn(),
  syncCatalog: vi.fn(),
  updateCatalogConnector: vi.fn(),
  queryKeys: {
    skills: { list: () => ['skills', 'list'] },
    extensions: {
      connectors: () => ['extensions', 'connectors', 'servers'],
      catalog: (kind: string, q = '') => ['extensions', 'catalog', kind, q],
      catalogStatus: () => ['extensions', 'catalog', 'status'],
    },
  },
  useDeleteSkill: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useSkills: () => useSkills(),
  useTrustSkill: () => ({ mutate: trustSkill, isPending: false }),
}));

const skill: CatalogSkill = {
  catalog_id: 'openai:pdf',
  name: 'pdf',
  display_name: 'PDF 工具',
  description: '处理 PDF 文件',
  source_id: 'openai',
  source_name: 'OpenAI',
  source_url: 'https://example.com/pdf',
  source_commit: 'abc',
  package_sha256: 'hash',
  compatibility_status: 'ready',
  warnings: [],
  has_scripts: false,
  synced_at: '2026-07-13T00:00:00Z',
  last_checked_at: '2026-07-13T00:00:00Z',
  withdrawn: false,
  installable: true,
  installed: false,
  update_available: false,
};

const connector: CatalogConnector = {
  catalog_id: 'mcp:filesystem',
  name: 'filesystem',
  display_name: '文件系统',
  description: '访问本地文件',
  source_id: 'mcp',
  source_name: 'MCP',
  source_url: 'https://example.com/filesystem',
  source_commit: 'abc',
  command: 'npx',
  args: ['server-filesystem'],
  env_schema: [],
  requirements: [],
  catalog_template_sha256: 'hash',
  synced_at: '2026-07-13T00:00:00Z',
  last_checked_at: '2026-07-13T00:00:00Z',
  withdrawn: false,
  installable: true,
  configured: false,
  update_available: false,
};

function renderPage(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <ExtensionCenterPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  installCatalogSkill.mockResolvedValue({});
  addCatalogConnector.mockResolvedValue({});
  listCatalogSkills.mockResolvedValue({ items: [skill], total: 1, page: 1, page_size: 100 });
  listCatalogConnectors.mockResolvedValue({
    items: [connector],
    total: 1,
    page: 1,
    page_size: 100,
  });
  useSkills.mockReturnValue({ data: { skills: [] }, isLoading: false });
  trustSkill.mockImplementation((_variables, options) =>
    options?.onSuccess?.({
      level: 'user_trusted',
      valid: true,
      package_sha256: 'hash',
      principal_id: 'local-user',
      trusted_at: '2026-07-14T08:00:00Z',
    }),
  );
});

afterEach(cleanup);

describe('ExtensionCenterPage catalog actions', () => {
  it('shows the SkillHub summary after the skill is installed', () => {
    useSkills.mockReturnValue({
      data: {
        skills: [{
          name: 'pdf',
          display_name: 'PDF 工具',
          description: 'Create, edit, and inspect PDF files',
          summary_zh: '创建、编辑并检查 PDF 文件',
          description_zh: '用于创建、编辑和检查 PDF 文件及其页面布局。',
          file_count: 1,
          bytes: 100,
          added_at: '2026-07-13T00:00:00Z',
          package_sha256: 'hash',
        } satisfies SkillMeta],
      },
      isLoading: false,
    });

    renderPage('/settings/skills');

    expect(screen.getByText('创建、编辑并检查 PDF 文件')).toBeTruthy();
    expect(screen.queryByText('Create, edit, and inspect PDF files')).toBeNull();
    fireEvent.click(screen.getByText('PDF 工具'));
    expect(screen.getByText('用于创建、编辑和检查 PDF 文件及其页面布局。')).toBeTruthy();
  });

  it('adds a SkillHub skill from its card', async () => {
    renderPage('/settings/skills');
    fireEvent.click(screen.getByRole('button', { name: 'SkillHub' }));
    await screen.findByText('PDF 工具');

    fireEvent.click(screen.getByRole('button', { name: '添加' }));

    await waitFor(() => expect(installCatalogSkill).toHaveBeenCalledWith(skill));
  });

  it('shows the trusted version status immediately after trusting a skill', () => {
    useSkills.mockReturnValue({
      data: {
        skills: [
          {
            name: 'docx',
            display_name: 'Word 文档',
            description: '创建 Word 文档',
            scripts: ['scripts/create.py'],
            file_count: 2,
            bytes: 200,
            added_at: '2026-07-13T00:00:00Z',
            package_sha256: 'hash',
            trust: { level: 'untrusted', valid: false, package_sha256: 'hash' },
          } satisfies SkillMeta,
        ],
      },
      isLoading: false,
    });

    renderPage('/settings/skills');
    fireEvent.click(screen.getByText('Word 文档'));
    fireEvent.click(screen.getByRole('button', { name: '信任当前版本' }));

    expect(trustSkill).toHaveBeenCalledWith(
      { name: 'docx', packageSha256: 'hash' },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(screen.getByText('已信任该技能版本')).toBeTruthy();
    expect(screen.getByText('信任时间')).toBeTruthy();
  });

  it('adds an available connector from its card with the current revision', async () => {
    renderPage('/settings/connectors');
    fireEvent.click(screen.getByRole('button', { name: '可用连接器' }));
    await screen.findByText('文件系统');

    fireEvent.click(screen.getByRole('button', { name: '添加' }));

    await waitFor(() => expect(addCatalogConnector).toHaveBeenCalledWith(connector, 7));
  });
});

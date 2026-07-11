import { apiGet, apiPost, withQuery } from './client';
import type { CatalogConnector, CatalogPage, CatalogSkill, CatalogSource, CatalogStatus } from '@/types/api/extensions';

export const listCatalogSources = () => apiGet<{ sources: CatalogSource[] }>('/extension-catalog/sources');
export const getCatalogStatus = () => apiGet<CatalogStatus>('/extension-catalog/status');
export const syncCatalog = (sourceId?: string, force = false) => apiPost<{ run_id: string; status: string }>(sourceId ? `/extension-catalog/sources/${encodeURIComponent(sourceId)}/sync` : '/extension-catalog/sync', { force });
export const listCatalogSkills = (q = '') => apiGet<CatalogPage<CatalogSkill>>(withQuery('/extension-catalog/skills', { q, page_size: 100 }));
export const installCatalogSkill = (item: CatalogSkill) => item.update_available
  ? apiPost(`/extension-catalog/skills/${encodeURIComponent(item.catalog_id)}/update`, { expected_package_sha256: item.package_sha256 })
  : apiPost(`/extension-catalog/skills/${encodeURIComponent(item.catalog_id)}/install`, {});
export const listCatalogConnectors = (q = '') => apiGet<CatalogPage<CatalogConnector>>(withQuery('/extension-catalog/connectors', { q, page_size: 100 }));
export const addCatalogConnector = (item: CatalogConnector, expectedRevision?: number) => apiPost(`/extension-catalog/connectors/${encodeURIComponent(item.catalog_id)}/add`, { expected_revision: expectedRevision });
export const previewCatalogConnectorUpdate = (item: CatalogConnector) => apiGet<{ revision: number; catalog_template_sha256: string; changes: Record<string, { before: unknown; after: unknown }> }>(withQuery(`/extension-catalog/connectors/${encodeURIComponent(item.catalog_id)}/update-preview`, { configured_name: item.configured_name }));
export const updateCatalogConnector = (item: CatalogConnector, revision: number, templateHash: string) => apiPost(`/extension-catalog/connectors/${encodeURIComponent(item.catalog_id)}/update`, { configured_name: item.configured_name, expected_revision: revision, expected_catalog_template_sha256: templateHash });

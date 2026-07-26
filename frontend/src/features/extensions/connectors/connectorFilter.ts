import type { McpServer } from '@/types';

export function connectorMatchesQuery(server: McpServer, query: string): boolean {
  if (!query) return true;
  return `${server.name} ${server.command} ${server.args.join(' ')}`
    .toLowerCase()
    .includes(query.toLowerCase());
}

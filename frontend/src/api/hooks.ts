import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { listSkills } from './skills';
import {
  deleteMcpServer,
  listMcpServers,
  reconnectMcpServer,
  upsertMcpServer,
} from './mcp';

export const useSkills = () => useQuery({ queryKey: ['skills'], queryFn: listSkills });

export const useMcpServers = () =>
  useQuery({ queryKey: ['mcp-servers'], queryFn: listMcpServers });

/** Every mutation republishes capabilities, so the list is always refetched. */
function useMcpMutation<TArgs>(fn: (args: TArgs) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['mcp-servers'] }),
  });
}

export const useUpsertMcpServer = () => useMcpMutation(upsertMcpServer);
export const useDeleteMcpServer = () => useMcpMutation(deleteMcpServer);
export const useReconnectMcpServer = () => useMcpMutation(reconnectMcpServer);

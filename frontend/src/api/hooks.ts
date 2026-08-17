import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { deleteSkill, listSkills, revokeSkillTrust, trustSkill } from './skills';
import { deleteMcpServer, listMcpServers, reconnectMcpServer, upsertMcpServer } from './mcp';
import { getModels, saveModels, testModelProvider } from './models';

export const SKILLS_KEY = ['skills'] as const;
export const MCP_SERVERS_KEY = ['mcp-servers'] as const;
export const MODELS_KEY = ['models'] as const;

export const useModels = () => useQuery({ queryKey: MODELS_KEY, queryFn: getModels });

export const useSkills = () => useQuery({ queryKey: SKILLS_KEY, queryFn: listSkills });

export const useMcpServers = () => useQuery({ queryKey: MCP_SERVERS_KEY, queryFn: listMcpServers });

/** Every mutation republishes capabilities, so the list is always refetched. */
function useInvalidatingMutation<TArgs, TResult>(
  key: readonly unknown[],
  fn: (args: TArgs) => Promise<TResult>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}

export const useSaveModels = () => useInvalidatingMutation(MODELS_KEY, saveModels);

/** Probing a connection changes nothing, so it deliberately invalidates nothing. */
export const useTestModelProvider = () => useMutation({ mutationFn: testModelProvider });

export const useUpsertMcpServer = () => useInvalidatingMutation(MCP_SERVERS_KEY, upsertMcpServer);
export const useDeleteMcpServer = () => useInvalidatingMutation(MCP_SERVERS_KEY, deleteMcpServer);
export const useReconnectMcpServer = () =>
  useInvalidatingMutation(MCP_SERVERS_KEY, reconnectMcpServer);

/**
 * Skill administration shares `['skills']` with the Composer's picker, so a
 * trust change or an uninstall is reflected there without a second fetch.
 */
export const useTrustSkill = () =>
  useInvalidatingMutation(SKILLS_KEY, (name: string) => trustSkill(name, true));
export const useRevokeSkillTrust = () => useInvalidatingMutation(SKILLS_KEY, revokeSkillTrust);
export const useDeleteSkill = () => useInvalidatingMutation(SKILLS_KEY, deleteSkill);

/** Lets the two-phase import flow refresh the shared list once it finishes. */
export function useInvalidateSkills() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: SKILLS_KEY });
}

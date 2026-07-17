export interface McpConnector { name: string; endpoint: string }
export interface AgentPreferences { model: string; personality: string; connectors: McpConnector[] }
const key = 'maestro.agent.preferences.v1';
const defaults: AgentPreferences = { model: '', personality: '', connectors: [] };
export function loadPreferences(): AgentPreferences { try { return { ...defaults, ...(JSON.parse(localStorage.getItem(key) ?? '{}') as Partial<AgentPreferences>) }; } catch { return defaults; } }
export function savePreferences(value: AgentPreferences) { localStorage.setItem(key, JSON.stringify(value)); }

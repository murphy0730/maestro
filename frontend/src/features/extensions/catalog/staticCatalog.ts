/**
 * 静态浏览目录 —— 后端还没有 `/skillhub` 与 `/mcp/catalog`，这里不伪造网络请求。
 *
 * 数据结构与未来的目录响应同形，方便接入时整体替换；条目只能「查看」，
 * 远程安装按钮不存在。默认关闭：`VITE_EXTENSION_CATALOG=on` 才渲染浏览页。
 */

export interface CatalogSkill {
  name: string;
  display_name: string;
  description: string;
  publisher: string;
  version: string;
  category: string;
}

export interface CatalogConnector {
  id: string;
  name: string;
  description: string;
  publisher: string;
  /** 模板只带命令与环境变量名，永远不含密钥值。 */
  command: string;
  args: string[];
  env_keys: string[];
}

export const CATALOG_CATEGORIES: Array<{ key: string; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'manufacturing', label: '制造运营' },
  { key: 'scheduling', label: '排产调度' },
  { key: 'analytics', label: '数据分析' },
  { key: 'knowledge', label: '知识查询' },
];

export const CATALOG_SKILLS: CatalogSkill[] = [
  {
    name: 'scheduling-query',
    display_name: '排产查询',
    description: '订单 / 工序 / 设备三维排程问答：甘特口径、前后序追溯、瓶颈定位。',
    publisher: 'Maestro 官方',
    version: 'v1.3.0',
    category: 'scheduling',
  },
  {
    name: 'capacity-report',
    display_name: '产能日报',
    description: '汇总订单、任务令与齐套数据，生成产能利用率与瓶颈分析报告。',
    publisher: 'Maestro 官方',
    version: 'v1.2.0',
    category: 'scheduling',
  },
  {
    name: 'mes-daily-digest',
    display_name: 'MES 每日摘要',
    description: '聚合报工、异常工单与质量数据，生成班前会可用的车间日报。',
    publisher: '企业内部',
    version: 'v2.1.0',
    category: 'manufacturing',
  },
  {
    name: 'oee-insight',
    display_name: 'OEE 洞察',
    description: '从稼动率、性能、良品三率拆解 OEE，定位损失主因并生成改善清单。',
    publisher: '社区',
    version: 'v0.6.3',
    category: 'analytics',
  },
  {
    name: 'bom-explainer',
    display_name: 'BOM 结构问答',
    description: '自然语言查询 BOM 层级、替代料与用量，支持按产品族追溯。',
    publisher: '企业内部',
    version: 'v0.7.4',
    category: 'knowledge',
  },
];

export const CATALOG_CONNECTORS: CatalogConnector[] = [
  {
    id: 'maestro-mes',
    name: 'Maestro MES',
    description: '查询订单、库存和工单信息，回写报工与异常。',
    publisher: 'Maestro',
    command: 'python',
    args: ['/opt/maestro/mes_mcp.py'],
    env_keys: ['MES_BASE_URL', 'MES_API_KEY'],
  },
  {
    id: 'llm4drd-scheduler',
    name: 'llm4drd 排产引擎',
    description: '读取订单排程甘特与工序前后序关系。',
    publisher: '内部',
    command: 'python',
    args: ['/opt/llm4drd/mcp_server.py'],
    env_keys: ['LLM4DRD_BASE_URL'],
  },
  {
    id: 'filesystem',
    name: '本地文件系统',
    description: '官方参考实现，把一个目录以 MCP 工具的形式挂给 Runtime。',
    publisher: 'Model Context Protocol',
    command: 'npx',
    args: ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'],
    env_keys: [],
  },
];

/** 浏览视图默认关闭，因为它背后没有真实后端。 */
export function catalogEnabled(): boolean {
  return import.meta.env.VITE_EXTENSION_CATALOG === 'on';
}

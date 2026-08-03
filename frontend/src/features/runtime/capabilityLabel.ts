import { useMemo } from 'react';
import { useMcpServers, useSkills } from '@/api';
import { PENDING_CAPABILITY_KIND } from '@/stores/runStore';
import type { McpServer, RunStep, SkillMeta, StepStatus } from '@/types';

/**
 * 能力注册名 → 人读文案。
 *
 * 运行轨迹里流过的是注册名（`mcp__jira__create_issue`、`skill_read_resource`、
 * `bash`），那是给模型看的命名空间，不是给人看的。这里把它翻译成「标题 + 来源 +
 * 风险」，原始名仍旧保留在 `raw` 里由 UI 折叠展示 —— 翻译是为了可读，不是为了藏。
 *
 * 元数据全部来自已有的只读端点：MCP 工具查 `GET /mcp/servers`，技能查 `GET /skills`，
 * 本机原语查下面这张词典。SSE 事件里没有这些字段，也不需要它有。
 */

export type CapabilityFamily = 'mcp' | 'tool' | 'skill' | 'unknown';

export interface CapabilityLabel {
  family: CapabilityFamily;
  /** 人读主标题：「创建议题」/「读取文件」。解析不出来时就是原始名。 */
  title: string;
  /** 来源：「Jira · 连接器」/「本机工具」/「技能」。 */
  source: string;
  /** 原始注册名，展开后显示。 */
  raw: string;
  description?: string;
  risk?: 'low' | 'medium' | 'high';
  writes?: boolean;
}

export interface CapabilityDirectory {
  servers?: McpServer[];
  skills?: SkillMeta[];
}

export const MCP_PREFIX = 'mcp__';

/** 步骤状态的中文文案 —— 运行轨迹与对话流共用一套，避免两处说法不一致。 */
export const stepLabels: Record<StepStatus, string> = {
  pending: '等待',
  ready: '就绪',
  waiting_approval: '待审批',
  running: '运行中',
  waiting_external: '等待外部',
  reconciling: '对账中',
  succeeded: '成功',
  failed: '失败',
  cancelled: '已取消',
  skipped: '已跳过',
};

/** `StepRecord.error_kind` 的中文文案；未知取值原样透出。 */
const errorKindLabels: Record<string, string> = {
  schema_input: '参数不合法',
  business_blocked: '业务拒绝',
  authorization: '未授权',
  transient_infrastructure: '基础设施故障',
  unknown_or_bug: '未知错误',
};

export function errorKindLabel(kind?: string | null): string | undefined {
  if (!kind) return undefined;
  return errorKindLabels[kind] ?? kind;
}

interface BuiltinTool {
  title: string;
  description: string;
  source: string;
  writes: boolean;
  risk: 'low' | 'medium' | 'high';
}

/**
 * `bootstrap.py::build_platform()` 注册的全部宿主原语。后端加了新原语就往这里补一条；
 * 漏了也只是退化成显示原始名，不会出错。
 */
const BUILTIN_TOOLS: Record<string, BuiltinTool> = {
  read_file: {
    title: '读取文件',
    description: '读取工作区内的一个文件',
    source: '本机工具',
    writes: false,
    risk: 'low',
  },
  glob: {
    title: '查找文件',
    description: '按通配符在工作区内查找文件',
    source: '本机工具',
    writes: false,
    risk: 'low',
  },
  grep: {
    title: '搜索内容',
    description: '在工作区文件内容里搜索',
    source: '本机工具',
    writes: false,
    risk: 'low',
  },
  write_file: {
    title: '写入文件',
    description: '在工作区内新建或覆盖一个文件',
    source: '本机工具',
    writes: true,
    risk: 'high',
  },
  edit_file: {
    title: '编辑文件',
    description: '替换工作区内某个文件的片段',
    source: '本机工具',
    writes: true,
    risk: 'high',
  },
  read_artifact: {
    title: '读取产物',
    description: '取回内容过大而未内联的调用结果',
    source: '本机工具',
    writes: false,
    risk: 'low',
  },
  bash: {
    title: '执行命令',
    description: '在沙箱工作区内执行任意 shell 命令',
    source: '本机工具',
    writes: true,
    risk: 'high',
  },
  get_current_time: {
    title: '查询当前时间',
    description: '读取宿主的当前日期与时间',
    source: '本机工具',
    writes: false,
    risk: 'low',
  },
  skill_read_resource: {
    title: '读取技能资源',
    description: '按需载入技能包内的一个引用或脚本文件',
    source: '技能运行时',
    writes: false,
    risk: 'low',
  },
  skill_run_script: {
    title: '运行技能脚本',
    description: '在沙箱内执行技能包自带的脚本',
    source: '技能运行时',
    writes: true,
    risk: 'high',
  },
};

/** 描述文本可能很长；标题只取第一句，完整描述留在 `description` 里。 */
function firstSentence(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return '';
  const stop = trimmed.search(/[。；\n.;]/);
  const head = stop > 0 ? trimmed.slice(0, stop) : trimmed;
  return head.length > 40 ? `${head.slice(0, 40)}…` : head;
}

/**
 * MCP 注册名形如 `mcp__{server}__{tool}`，而服务器名和工具名本身都可能含 `__`，
 * 所以优先走精确匹配，切分只是查不到时的兜底。
 */
function describeMcp(name: string, servers: McpServer[]): CapabilityLabel {
  for (const server of servers) {
    for (const tool of server.tools ?? []) {
      if (tool.capability !== name) continue;
      return {
        family: 'mcp',
        title: firstSentence(tool.description) || tool.name,
        source: `${server.name} · 连接器`,
        raw: name,
        description: tool.description || undefined,
        risk: tool.risk,
        writes: tool.writes && !tool.read_only,
      };
    }
  }
  const rest = name.slice(MCP_PREFIX.length);
  const split = rest.indexOf('__');
  const server = split > 0 ? rest.slice(0, split) : rest;
  const tool = split > 0 ? rest.slice(split + 2) : '';
  return {
    family: 'mcp',
    title: tool || rest || name,
    source: server ? `${server} · 连接器未连接` : '连接器未连接',
    raw: name,
  };
}

export function describeCapability(
  name: string,
  directory: CapabilityDirectory = {},
): CapabilityLabel {
  if (!name) return { family: 'unknown', title: name, source: '', raw: name };
  // `write.started` 只带 step_id，能力名要等完成事件才到；期间别把占位符当能力名显示。
  if (name === PENDING_CAPABILITY_KIND)
    return { family: 'unknown', title: '能力调用', source: '', raw: name };

  if (name.startsWith(MCP_PREFIX)) return describeMcp(name, directory.servers ?? []);

  const builtin = BUILTIN_TOOLS[name];
  if (builtin) {
    return {
      family: 'tool',
      title: builtin.title,
      source: builtin.source,
      raw: name,
      description: builtin.description,
      risk: builtin.risk,
      writes: builtin.writes,
    };
  }

  const skill = (directory.skills ?? []).find((item) => item.name === name);
  if (skill) {
    return {
      family: 'skill',
      title: skill.display_name || skill.name,
      source: '技能',
      raw: name,
      description: skill.summary_zh || skill.description || undefined,
    };
  }

  return { family: 'unknown', title: name, source: '', raw: name };
}

export type CapabilityDescribe = (name: string) => CapabilityLabel;

/** 没有目录时的退化解析：内置原语照常翻译，MCP 名靠切分兜底。 */
export const describeWithoutDirectory: CapabilityDescribe = (name) => describeCapability(name);

/**
 * 目录是两个已缓存的只读查询。只在 Workspace 这个组装点调用一次，再把 `describe`
 * 往下传 —— 展示组件因此不带数据依赖，测试里也不需要 QueryClientProvider。
 * 查询失败时退化为「只认得内置原语」，面板照常渲染。
 */
export function useCapabilityDirectory(): CapabilityDescribe {
  const servers = useMcpServers().data?.servers;
  const skills = useSkills().data?.skills;
  return useMemo(
    () => (name: string) => describeCapability(name, { servers, skills }),
    [servers, skills],
  );
}

/** 调用参数体积不设限，展示要设 —— 超长就截断，完整内容仍可从产物链接取。 */
export const ARGUMENTS_CHAR_LIMIT = 2000;

export function formatArguments(step: Pick<RunStep, 'call'>): string | undefined {
  const args = step.call?.arguments;
  if (!args || typeof args !== 'object' || Object.keys(args).length === 0) return undefined;
  let text: string;
  try {
    text = JSON.stringify(args, null, 2);
  } catch {
    return undefined;
  }
  return text.length > ARGUMENTS_CHAR_LIMIT
    ? `${text.slice(0, ARGUMENTS_CHAR_LIMIT)}\n… 已截断`
    : text;
}

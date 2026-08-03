import { describe, expect, it } from 'vitest';
import type { McpServer, SkillMeta } from '@/types';
import { describeCapability, errorKindLabel, formatArguments } from './capabilityLabel';

const jira: McpServer = {
  name: 'jira',
  command: 'jira-mcp',
  args: [],
  env_keys: [],
  enabled: true,
  read_only_tools: ['search_issues'],
  status: 'connected',
  error: '',
  tools: [
    {
      name: 'create_issue',
      capability: 'mcp__jira__create_issue',
      description: '创建议题。参数见 Jira REST v3。',
      read_only: false,
      writes: true,
      risk: 'high',
    },
    {
      name: 'search_issues',
      capability: 'mcp__jira__search_issues',
      description: '按 JQL 检索议题',
      read_only: true,
      writes: false,
      risk: 'low',
    },
  ],
};

describe('describeCapability', () => {
  it('resolves an MCP tool to its server, description and risk', () => {
    const label = describeCapability('mcp__jira__create_issue', { servers: [jira] });
    expect(label).toMatchObject({
      family: 'mcp',
      title: '创建议题',
      source: 'jira · 连接器',
      raw: 'mcp__jira__create_issue',
      risk: 'high',
      writes: true,
    });
  });

  it('does not mark a read-only MCP tool as a write', () => {
    const label = describeCapability('mcp__jira__search_issues', { servers: [jira] });
    expect(label.writes).toBe(false);
    expect(label.risk).toBe('low');
  });

  it('falls back to splitting the registry name when the server is gone', () => {
    // 服务器断开后 GET /mcp/servers 里就没有这个工具了，但轨迹里的历史步骤还在。
    const label = describeCapability('mcp__jira__create_issue', { servers: [] });
    expect(label.family).toBe('mcp');
    expect(label.title).toBe('create_issue');
    expect(label.source).toContain('jira');
    expect(label.source).toContain('未连接');
  });

  it('keeps a tool name containing __ intact by matching exactly', () => {
    const server: McpServer = {
      ...jira,
      name: 'a__b',
      tools: [
        {
          name: 'c__d',
          capability: 'mcp__a__b__c__d',
          description: '双下划线工具',
          read_only: true,
          writes: false,
          risk: 'low',
        },
      ],
    };
    const label = describeCapability('mcp__a__b__c__d', { servers: [server] });
    expect(label.title).toBe('双下划线工具');
    expect(label.source).toBe('a__b · 连接器');
  });

  it('translates every host primitive from the built-in dictionary', () => {
    expect(describeCapability('read_file')).toMatchObject({
      family: 'tool',
      title: '读取文件',
      source: '本机工具',
      writes: false,
    });
    expect(describeCapability('bash')).toMatchObject({
      family: 'tool',
      title: '执行命令',
      writes: true,
      risk: 'high',
    });
    // 技能运行时的两个原语归到技能那一侧，别混进「本机工具」。
    expect(describeCapability('skill_read_resource').source).toBe('技能运行时');
    expect(describeCapability('skill_run_script')).toMatchObject({
      source: '技能运行时',
      writes: true,
    });
  });

  it('prefers a skill display name and its Chinese summary', () => {
    const skill = {
      name: 'whatif-planning',
      display_name: '排产什么如果分析',
      description: 'What-if planning',
      summary_zh: '对排产方案做假设推演',
    } as SkillMeta;
    expect(describeCapability('whatif-planning', { skills: [skill] })).toMatchObject({
      family: 'skill',
      title: '排产什么如果分析',
      source: '技能',
      description: '对排产方案做假设推演',
    });
  });

  it('shows an unrecognised name as-is rather than hiding it', () => {
    const label = describeCapability('some_host_capability');
    expect(label).toMatchObject({ family: 'unknown', title: 'some_host_capability', source: '' });
  });
});

describe('formatArguments', () => {
  it('returns nothing when a step carries no call arguments', () => {
    // 只读能力不建 StepRecord，事件推导出的步骤本来就没有参数。
    expect(formatArguments({})).toBeUndefined();
    expect(formatArguments({ call: { name: 'read_file' } })).toBeUndefined();
    expect(formatArguments({ call: { name: 'read_file', arguments: {} } })).toBeUndefined();
  });

  it('pretty-prints and truncates oversized arguments', () => {
    const short = formatArguments({ call: { arguments: { path: 'a.txt' } } });
    expect(short).toBe('{\n  "path": "a.txt"\n}');

    const long = formatArguments({ call: { arguments: { blob: 'x'.repeat(4000) } } });
    expect(long?.endsWith('… 已截断')).toBe(true);
    expect(long!.length).toBeLessThan(2100);
  });
});

describe('errorKindLabel', () => {
  it('translates known error kinds and passes unknown ones through', () => {
    expect(errorKindLabel('authorization')).toBe('未授权');
    expect(errorKindLabel('brand_new_kind')).toBe('brand_new_kind');
    expect(errorKindLabel(undefined)).toBeUndefined();
    expect(errorKindLabel(null)).toBeUndefined();
  });
});

# 查询引擎 RAG 能力设计 v1

> 本文档为 `scheduling-platform-design-v3.md` §7B（QueryEngine）中「rerank / 混合检索 v0.2+」预留项的展开设计。
> 设计基线以**仓库现有代码**为准，不以任何外部模板假设为准。

---

## 0. 现状基线与假设清单

### 0.1 现有实现（代码事实，非假设）

| 组件 | 现状 | 位置 |
|---|---|---|
| 向量库 | 内存 list + 余弦相似度，接口 `add_texts / search` | `foundation/vectorstore.py` |
| 嵌入 | `EmbeddingClient`，`EMBED_MODEL` 未配置则整层退化为空检索 | `foundation/embedding.py` |
| 检索器 | 惰性加载 `data/mock/knowledge/*.md`，按**空行段落**切块，元数据仅 `{doc: 文件名}`，top_k=3 | `engines/query/retriever.py` |
| 查询引擎 | retrieve → augment（片段注入 system prompt）→ generate（LLM + 只读工具），降级为数据摘要 | `engines/query/query_engine.py` |
| 实时数据 | 已通过只读工具融合（`check_kitting / query_work_orders / query_inventory` 等，走 `IntegrationAdapter`） | `foundation/tools/builtin.py` |
| 技术栈 | Python 3.12 + FastAPI + OpenAI 兼容 LLM（默认 DeepSeek）+ Pydantic v2；**无** LangGraph / FastMCP | `config.py` / `pyproject.toml` |

现有痛点（由代码直接可见）：
1. 段落切块丢失标题上下文（"齐套率的计算公式"这一段脱离了它所属的章节标题，语义不完整）；
2. 元数据只有文档名，无法按产品线/异常类型/文档类型过滤；
3. 纯向量单路召回——调度术语（齐套、欠料、插单、改派、EDD、CP-SAT）是低频专业词，通用嵌入模型对其区分度差，且物料号/工单号（`M-1001`/`WO-123`）这类精确 token 向量检索基本必丢；
4. 检索无条件执行且结果无条件注入（top-3 无论相关与否都进 prompt）；
5. 无任何评估手段，改了检索策略好坏无从判断。

### 0.2 假设清单（提问中未填的占位符，按以下假设设计，**如与实际不符请修正后出 v2**）

- **A1 知识库构成**：① 制造业通用资料（Factory Physics、APS/MRP 理论、行业标准，PDF/Word，页数百级）；② 调度领域知识（排产规则说明、约束逻辑、策略/算法文档，Markdown/Word）；③ 实际工作案例（历史调度处置复盘、异常处理记录，半结构化）。
- **A2 典型 query**（覆盖四种形态）：
  - Q1「注塑线的排产逻辑是什么？为什么用模具约束建模？」（领域规则）
  - Q2「齐套率怎么算？和物料可用率有什么区别？」（概念定义）
  - Q3「类似 M-2001 这种长周期物料缺料，历史上是怎么处理的？」（案例检索）
  - Q4「2号线现在哪些任务缺料开不了工？」（纯实时，走工具不走知识库）
  - Q5「WO-123 为什么被排到下周？依据的排产规则是哪条？」（实时 + 知识混合）
- **A3 规模**：文档数百份、切块后 1万–10万 chunk 量级；单机可承载，不需要分布式检索。
- **A4 约束**：内网部署，LLM/嵌入走内部 API 网关（OpenAI 兼容）；查询端到端延迟目标 ≤ 5s（流式首 token ≤ 2s）；不引入需要独立运维的重型中间件（ES/Neo4j）除非收益明确。
- **A5 持久化**：假设可用 PostgreSQL 系数据库（含 GaussDB，兼容 pgvector 语义）；若不可用，退到本地 Chroma / sqlite-vec。

---

## 1. 总体架构

三层结构，全部落在现有 `QueryEngine` 的「retrieve → augment → generate」骨架内——**不新增引擎、不改 Orchestrator 路由、不动 EngineResponse 契约**：

```
                       离线（索引层, 新增 CLI 管线）
  PDF/Word/MD/案例记录 ──▶ 解析归一 ──▶ 结构感知切块 ──▶ 元数据抽取 ──▶ 嵌入
                                                            │
                                              ┌─────────────┴─────────────┐
                                              ▼                           ▼
                                        向量索引(pgvector/Chroma)    BM25 词法索引(内存/DB)
                                              │                           │
                       在线（检索层, 扩展 retriever.py）                    │
  用户 query ──▶ ①查询理解: 术语归一+指代消解+(可选)LLM改写               │
             ──▶ ②混合召回: 向量 top-N ⊕ BM25 top-N ──RRF融合──▶ 候选池 ◀─┘
             ──▶ ③元数据过滤(产品线/文档类型/时间)
             ──▶ ④rerank(可选层, RERANK_MODEL 未配置则跳过) ──▶ top-k + 相关性下限
                       在线（生成层, 现有 query_engine.py 微调）
             ──▶ ⑤augment: 知识片段/案例/实时工具数据 分区注入, 标来源
             ──▶ ⑥generate: LLM + 只读工具, 回答附引用; 冲突时实时数据优先
```

### 1.1 与现有架构的集成点（改哪、不改哪）

| 集成点 | 做法 |
|---|---|
| Orchestrator | **不改**。路由边界仍按 v3「是否有副作用」划分，RAG 全部发生在 QueryEngine 内部 |
| `VectorStore` | 保留 `add_texts / search` 接口，新增 `search(query, top_k, filters)` 的 filters 参数；内存实现之外新增 `PgVectorStore`（A5 不成立则 `ChromaStore`），在 `bootstrap.py` 换装配——与 `IntegrationAdapter` 换 Mock 同一模式 |
| `KnowledgeRetriever` | 演进为 `HybridRetriever`：内部持有向量库 + BM25 索引 + 可选 reranker，对 QueryEngine 暴露的 `search_passages` 签名不变 |
| 索引构建 | 从「首次检索惰性加载」改为**离线管线** `python -m scheduling_platform.ingest`（详见 §2.4）；惰性加载保留为 mock 知识的兜底 |
| 降级纪律 | 延续平台模式：`EMBED_MODEL` 未配 → 只走 BM25；`RERANK_MODEL` 未配 → 跳过 rerank；LLM 改写失败 → 用原始 query。**任何一层缺失系统仍可答** |
| 审计 | 每次检索的 query/改写结果/各路召回数/rerank 分数/最终引用进 `TraceLog`（步级），用户对答案的纠正进 `AuditLog`——复用 §4.6 双流 |

---

## 2. 索引层：文档处理与统一

### 2.1 多源异构统一：一切归一为「知识单元」

所有来源先转成**带 YAML frontmatter 的 Markdown**作为中间格式（人可读、可 diff、可进 git），再统一切块入库：

- PDF/Word（通用资料）：解析工具（如 `pymupdf` / `python-docx`，内网可装）→ Markdown，保留标题层级；表格转 Markdown 表格并整表成块。
- 排产规则/约束文档：本身多为 MD/Word，补 frontmatter。
- 案例记录：**不走自由文本**，用固定模板结构化（见 §4）。

### 2.2 切块策略：按文档类型分策略，不搞一刀切

| 文档类型 | 切块方式 | 理由 |
|---|---|---|
| 理论/通用资料 | 按**标题层级**切（H2/H3 为界），目标 300–500 token，超长段内部滑窗（overlap 15%） | 概念解释需要完整小节 |
| 排产规则/约束逻辑 | **一条规则 = 一个 chunk**（规则编号为界），禁止跨规则合并 | 规则是引用与执行的最小单位，Q1/Q5 类问题要能精确引到"哪条规则" |
| SOP/处置手册 | 一个处置流程（含全部步骤）= 一个 chunk，宁长勿断 | 截断的操作步骤比检索不到更危险 |
| 案例 | 一个案例 = 一条结构化记录 + 一个摘要 chunk（见 §4） | — |

**每个 chunk 前置拼接其标题链**（如 `注塑产线排产规则 > 模具约束 > 换模时间`），标题链同时进嵌入文本和 BM25——这是对现状「段落脱离标题」问题的直接修复，也是性价比最高的一项改动。

### 2.3 元数据 schema（调度领域结构化字段）

```python
class KnowledgeChunk(BaseModel):
    chunk_id: str
    text: str                      # 含标题链前缀
    doc_id: str
    doc_type: Literal["theory", "rule", "sop", "case"]
    title_path: list[str]          # 标题链
    # —— 调度领域字段（可空；rule/sop/case 必填其一以上）——
    product_lines: list[str]       # 关联产品线, 与主数据 line 口径一致, "*"=通用
    process: str | None            # 工序/环节: 排产/齐套/催料/下发/异常处置
    exception_types: list[str]     # 关联异常: material_shortage/equipment_alarm/quality_issue
    entities: list[str]            # 提及的物料号/工单号/策略名等精确实体
    objective: str | None          # 关联优化目标: min_tardiness/min_makespan...
    # —— 治理字段 ——
    source: str                    # 原始文件/系统
    effective_date: date | None    # 生效日期（规则类必填）
    superseded_by: str | None      # 规则被新版替代时指向新 chunk
    version: str
```

要点：
- **`product_lines` / `exception_types` 的取值域与平台主数据、`SystemEvent.type` 对齐**，不另造词表——这样事件层、调度引擎、知识库三方讲同一种语言，后续"事件唤醒时带知识"（§5.3）才接得上。
- 领域字段抽取：规则/案例类由模板强制填写（人填）；理论类由 LLM 离线批量抽取 + 抽样人审。
- `effective_date` / `superseded_by`：排产规则会改版，检索默认过滤已废止规则——答错"旧规则"比答不出更伤信任。

### 2.4 索引管线（离线 CLI）

```
python -m scheduling_platform.ingest --source docs/knowledge/ [--rebuild | --incremental]
```

- 增量：按文件内容 hash 判断变更，只重嵌入变更文档的 chunk。
- 索引带版本号；重建在影子索引完成后原子切换，在线查询不中断。
- 管线产物落库（pgvector 表 + BM25 索引持久化），FastAPI 启动时只加载、不构建——修复现状「首个查询触发全量嵌入」的延迟毛刺。

### 2.5 存储选型

- **首选 pgvector**（GaussDB 向量能力同理）：向量 + 元数据过滤 + 全文检索一库搞定，运维面最小，符合 A4「不引入重型中间件」。
- 不可用则 **Chroma 本地持久化**（向量+metadata filter），BM25 用 `bm25s`/`rank_bm25` 进程内索引（10万 chunk 量级毫秒级，完全够用，**不上 Elasticsearch**）。
- 无论哪种，业务侧只见 `VectorStore` 接口，`bootstrap.py` 换实现。

---

## 3. 检索层

### 3.1 查询理解与改写（轻量优先，能不调 LLM 就不调）

按序三步，每步可独立降级：

1. **术语归一（词典，零成本）**：维护领域同义词典 `terminology.yaml`——`缺料/欠料/短料 → 缺料`，`催料/加急/催货 → 催料`，`齐套/配套/kitting → 齐套`，缩写展开（`EDD → 最早交期优先(EDD)`）。同一词典喂给 jieba 用户词典（BM25 分词用）与 BM25 查询扩展。**词典与 §2.3 领域字段取值域同源维护**。
2. **实体提取（正则，零成本）**：`WO-\d+ / O\d+ / M-\d+ / 产线名` 直接提出来——既做 BM25 精确匹配加权，又做元数据 filter（Q3 的 `M-2001` 靠这个，不靠向量）。
3. **LLM 改写（仅多轮指代时启用）**：会话历史中存在指代（"那它的处理流程呢？"）才调 LLM 把 query 补全为自包含问句；单轮完整问句跳过。失败降级用原句。复杂 query 分解（multi-hop）**不做**，列 TODO——当前 query 形态（A2）没有强 multi-hop 需求，别为想象中的问题买单。

### 3.2 混合召回 + RRF 融合

- 向量路：改写后 query → 嵌入 → top-20。
- BM25 路：jieba（+用户词典）分词 → top-20；命中 §3.1 提取实体的 chunk 加权。
- 融合：**RRF（k=60）**，实现十行以内，无需调权重超参。
- 融合后过元数据 filter：默认滤掉 `superseded_by != null`；query 中识别出产品线/异常类型时按字段收窄（软过滤：命中加分而非硬排除，防止元数据填写不全导致漏召回）。

为什么必须混合：调度术语与编号类实体是词法信号强、语义信号弱的典型场景，BM25 补向量的短板；反过来"类似场景怎么处理"这类改述查询靠向量。两路互补，RRF 融合是该规模下最稳妥的免调参方案。

### 3.3 Rerank（可选层，仿 `EMBED_MODEL` 模式）

- 候选池 top-20~40 → cross-encoder 重排 → top-5 进 prompt。
- 配置 `RERANK_MODEL`（内网部署 bge-reranker-v2-m3 类模型，或 API 网关如提供 rerank 端点则直接用）；**未配置则跳过整层**，RRF 结果直接截断使用。
- **相关性下限**：rerank 分数（无 rerank 时用 RRF 归一分）低于阈值的片段不进 prompt；全部低于阈值 → 明确走"知识库检索不到"分支，让 LLM 如实说明或转工具——修复现状「top-3 无条件注入」的噪声问题，也直接支撑 v3 验收项"检索不到不编造"。

### 3.4 检索决策：谁决定查不查知识库

现状是"每问必检索"。改为 QueryEngine 内部先做一次**轻分类**（规则优先，规则不中才 LLM）：

- query 含实体编号 + 状态动词（"WO-123 现在什么状态"）→ 纯工具，跳过检索（Q4）；
- 概念/规则/历史疑问词（"是什么/怎么算/为什么/历史上"）→ 检索（Q1/Q2/Q3）；
- 混合形态（Q5）→ 两者都做，分区注入。

规则覆盖不了的兜底：都做（宁多勿漏），靠 §3.3 相关性下限把无关片段拦在 prompt 外。

---

## 4. 案例知识：结构化检索优先，不上 GraphRAG

### 4.1 判断

GraphRAG 的收益场景是「大规模非结构化语料 + 跨文档多跳关系问答」。本平台的案例是**天然可结构化的运营记录**（一次异常处置 = 触发事件 + 场景特征 + 处置动作 + 结果），数量千级以内，查询形态是"找相似案例"（Q3）而非多跳推理。上 GraphRAG（图构建、社区摘要、Neo4j 运维）成本远超收益，且违反 A4。**结论：案例走「结构化案例卡 + 混合检索」，GraphRAG 不做**；若未来出现真正的多跳需求（"这条规则的历史修订原因链"），先用 §2.3 的 `entities` 字段做轻量实体倒排索引过渡。

### 4.2 案例卡模板（半结构化 → 结构化）

```yaml
case_id: CASE-2026-0142
title: 长周期物料 M-2001 缺料导致 WO 批量延期的处置
occurred_at: 2026-03-14
product_lines: [注塑]
exception_types: [material_shortage]
entities: [M-2001, WO-311, WO-312]
scenario: |      # 场景特征（嵌入检索的主体）
  长采购周期物料缺料，影响 3 个已排产 WO，交期均在 7 天内
root_cause: 供应商产能不足，MRP 提前期参数未更新
actions:         # 处置动作序列（结构化，可复用为调度引擎建议）
  - 供应商催料（升级至采购主管）
  - 部分 WO 改用替代料 M-2001B（工艺确认后）
  - 剩余 WO 重排至下周期
outcome: 2 单准交，1 单延 2 天；后续更新了 M-2001 提前期参数
lessons: 长周期料应纳入预测性齐套扫描的更长提前期窗口
```

- 入库双份：结构化记录进案例表（按 `product_lines`/`exception_types`/`entities` 精确过滤），`title + scenario + root_cause + lessons` 拼接为摘要 chunk 进混合索引。
- 检索 Q3 时：实体/异常类型过滤（结构化）∩ 场景相似（向量）→ 案例卡整卡注入 prompt（案例不截断）。
- **来源治理**：新案例由调度引擎的处置记录（`record_followup` + AuditLog）半自动生成草稿、人工复核入库——案例库随平台运行自增长，这是本平台相对通用 RAG 的独有闭环。

---

## 5. 与实时调度数据的融合

### 5.1 原则：分工不越界

- **实时事实（库存/工单/齐套/计划）只来自只读工具**（走 `IntegrationAdapter`，未来即 MES/ERP 真实接口）——知识库永远不做实时事实来源，文档里的数字一律视为示例。
- **知识库供"解释框架"**：规则为什么这样、概念如何定义、历史如何处置。
- Prompt 分区注入并显式声明优先级（在现有 `QUERY_SYSTEM` 上扩展）：

```
【知识库参考】(带来源+生效日期) ...
【实时数据】(带工具名+查询时间) ...
规则: 数据类问题以【实时数据】为准; 两区冲突时以实时数据为准并指出文档可能过时;
回答须标注每个结论依据哪个分区哪条来源。
```

### 5.2 Q5 类混合查询的执行形态

"WO-123 为什么排到下周？"——LLM 先调工具取 WO-123 所属 plan 与策略名（`PlanStore` 已有 `strategy_name`/`objective`），再以策略名+产品线为条件补一次检索取对应规则 chunk，综合作答并双向引用。实现上即现有 tool-loop 内**允许 LLM 把「检索知识库」本身作为一个只读工具调用**（`search_knowledge(query, filters)` 注册进 ToolRegistry 只读白名单）——检索从"每问一次前置"变为"LLM 可按需多次"，这是对 agentic RAG 的最小实现，不需要引入任何新框架。

### 5.3 预留：事件路径复用（不在本期）

调度引擎被事件唤醒处置异常时，可用同一 `search_knowledge` 工具按 `exception_types` 取 SOP/相似案例作为处置参考——因为 §2.3 元数据与事件类型同口径，此项打开即用。列 TODO(v0.3)。

---

## 6. 评估方案

### 6.1 检索质量（离线，进 pytest，不调真实 LLM）

- **金标集**：50–100 条 query（覆盖 A2 五种形态 + 术语变体 + 编号实体），每条标注相关 chunk_id 集合。由领域用户标注，误判回流（AuditLog 中用户纠正的问题）持续补充。
- 指标：**Recall@5**（主指标，rerank 前候选池另测 Recall@20 定位是召回还是排序的锅）、**MRR**、按 query 类型分桶报告（术语类/实体类/改述类分开看，才知道 BM25 和向量各自拖没拖后腿）。
- 嵌入可 mock 时跑 BM25 路的确定性断言（编号实体类 query 必须 Recall@5=1.0）；嵌入相关指标用固定嵌入缓存离线跑。
- 每次改检索策略（换嵌入模型/调 chunk 大小/加 rerank）先跑金标集，指标不降才合入——这是本设计所有后续迭代的闸门。

### 6.2 答案质量（离线批跑 + 在线抽样）

- **忠实度（faithfulness）**：答案中每个论断是否有注入片段/工具结果支撑——LLM-as-judge 按论断逐条判定，输出无支撑论断比例。
- **引用正确率**：标注的来源是否真的包含对应内容。
- **拒答正确率**：金标集中混入 10–20 条知识库确实没有答案的问题，验证"如实说明不掌握"而非编造（对应 v3 验收项）。
- 判卷模型用与生成不同的模型（或至少不同 prompt 角色），结果抽样人审校准。

### 6.3 在线反馈闭环

- 每次查询的完整检索轨迹进 TraceLog（§1.1），回答附带的来源随 `EngineResponse.data.sources` 返回（现有字段，前端可做引用展示与"没帮到我"反馈按钮）。
- 用户纠正/差评样本 → 回流金标集 → 下轮迭代。与 v3 路由层"误判回流"同一机制。

---

## 7. 实施路线(每期独立可验收)

| 期 | 内容 | 验收 |
|---|---|---|
| **P1（先做，性价比最高）** | 标题层级切块+标题链前缀；元数据 schema + filter；ingest CLI + 持久化向量库；金标集 v1 + Recall@5 基线 | 金标集 Recall@5 相比现状基线提升；启动无嵌入毛刺 |
| **P2** | jieba+术语词典；BM25 路 + RRF；实体正则提取与加权；检索决策轻分类 | 实体类 query Recall@5=1.0；术语变体类显著提升 |
| **P3** | rerank 可选层 + 相关性下限；LLM 指代改写；`search_knowledge` 注册为只读工具（Q5 形态） | 忠实度/拒答正确率达标；Q5 类问题可双向引用 |
| **P4** | 案例卡模板 + 案例结构化检索 + 处置记录半自动生成草稿 | Q3 类问题可返回相似案例卡 |

每期均保持降级纪律：任何新增层（BM25 之外的嵌入、rerank、LLM 改写）缺配置即跳过，系统可答。

## 8. 开放问题（需业务方确认）

1. §0.2 假设 A1–A5 的核实，尤其数据规模（决定是否要重新评估存储选型）与内网可部署的 rerank 模型。
2. 排产规则文档目前是否存在权威唯一来源？若规则散落多文档且互相矛盾，需先做一次规则文档治理（`effective_date`/`superseded_by` 才有得填）。
3. 历史案例的原始形态（有无现成记录系统？量级？）——决定 P4 是模板补录还是批量迁移。
4. 金标集标注人力（约 2 人日）的安排。

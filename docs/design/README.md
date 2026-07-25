# 设计系统

`maestro-design-system-v2.html` —「深空指挥舱」— 是前端视觉的**唯一事实来源**，已落地到代码。双击即可离线打开：字体（Space Grotesk / JetBrains Mono）以 base64 内嵌，无任何外部请求。

`maestro-design-system-v1.html` 保留存档，仅供追溯，**不要**据它写新代码。v2 与 v1 无继承关系，是按 Agent Runtime 现状（runs / approvals / skills / sessions）从零设计的。

页面本身就是设计稿：所有色值、字号、圆角、间距都由页内 CSS 变量直接渲染，不是截图。改这个文件 = 改设计。

## 规范速查

以 `frontend/src/index.css` 的实际 token 为准（下表为深色默认值；浅色在同文件的 `[data-theme='light']` 里同构定义）。

| 维度 | 规则 |
| --- | --- |
| 主题 | **深色默认**（`--bg-base: #04060d`），浅色为同级方案而非降级，经 `[data-theme]` 切换 |
| 主强调 青 `#29d8ff` | `--accent`：品牌、主按钮、焦点环、发光（`--glow-accent`） |
| 授权 | `--auth-auto` 绿 `#3ce59b`（自动放行） / `--auth-confirm` 琥珀 `#ffc53d`（需人工确认） |
| 状态 | success `#3ce59b` / warning `#ffc53d` / error `#ff6473` / info `#5ea2ff`，各带 `-bg` 低透明底 |
| 执行路径 | `--path-controlled` 紫 `#a78bfa` 标记受控执行；快速循环不着色 |
| 运行模式 | `--mode-planning` `#5ea2ff` / `--mode-scheduling` `#ffa94d` / `--mode-query` `#2dd4bf` |
| 图表序列 | `--data-1..6`，青→紫→蓝→绿→琥珀→红 |
| 圆角 | xs 4 / sm 6 / md 8 / lg 12 / xl 16 / pill |
| 间距 | **刻度被重定义**：`1`=2px、`2`=4px、`3`=6px、`4`=8px、`5`=12px、`6`=16px…… 不是 Tailwind 默认的 4px×n |
| 字号 | display 40 / h1 30 / h2 24 / h3 20 / h4 16 / body-lg 16…… 见 `tailwind.config.ts` 的 `fontSize` |

字体：标题与正文同用 Space Grotesk Variable（中文回落 PingFang SC / HarmonyOS Sans SC），等宽用 JetBrains Mono Variable。
**中文字重封顶 500、字距归零**——PingFang SC 无真 SemiBold，600 会触发伪粗体。

品牌标记是指挥棒（Maestro = 指挥家）：握棒支点 + 扬起的棒 + 两道淡出的手势轨迹。

## 与代码的对应

设计 token 在 `frontend/src/index.css` 定义，`frontend/tailwind.config.ts` 把它们镜像成语义工具类。组件里只用语义类（`bg-surface-2`、`text-auth-confirm`、`shadow-glow-accent`…），不写裸 hex。

修改设计稿后请同步这两个文件。新版本另存为 `maestro-design-system-v3.html`，不要覆盖旧版。

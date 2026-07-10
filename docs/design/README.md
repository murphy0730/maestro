# 设计系统

`maestro-design-system-v1.html` 是前端视觉的**唯一事实来源**。双击即可离线打开——字体（Geist / Inter / Geist Mono）以 base64 内嵌，无任何外部请求。

页面本身就是设计稿：所有色值、字号、圆角、间距都由页内 CSS 变量直接渲染，不是截图。改这个文件 = 改设计。

## 规范速查

| 维度 | 规则 |
| --- | --- |
| 蓝 `#2F6FEB` | 沟通与导航：我的气泡、发送、新建对话、排产 route、品牌色 |
| 绿 `#16A34A` | 执行：提交排产方案、直接下发、成功状态、`auto` 授权 |
| 琥珀 `#B45309`（深色 `#FFC53D`） | 待确认：`requires_confirmation` 授权、产能告警 |
| 红 `#DC2626`（深色 `#FF6369`） | 阻塞：缺料、危险操作 |
| 橙 `#C2620A` / 青 `#0E8E7F` / 灰 `#6E7379` | 调度 / 查询 / 不确定 三条 route |
| 圆角 | 4 / 6 / 8 / 12 / pill |
| 间距 | 4px 基准网格 |
| 主题 | 浅色默认，深色跟随系统或 `[data-theme]` 手动切换 |

字体：标题 Geist 600（`-0.02em`），正文 Inter 400–500，数字与工单号 Geist Mono（tabular）。
**中文字重封顶 500、字距归零**——PingFang SC 无真 SemiBold，600 会触发伪粗体。

品牌标记是指挥棒（Maestro = 指挥家）：握棒支点 + 扬起的棒 + 两道淡出的手势轨迹。

## 与代码的对应

设计 token 在 `frontend/src/index.css` 定义，`frontend/tailwind.config.ts` 把它们镜像成语义工具类。组件里只用语义类（`bg-planning`、`text-auth-confirm`…），不写裸 hex。

修改设计稿后请同步这两个文件。新版本另存为 `maestro-design-system-v2.html`，不要覆盖旧版。

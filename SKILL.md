---
name: myou-data-research
version: "2.3.0"
display_name: MYOU网络情报分析师
display_name_en: Data Research Methodology
description_zh: >
  纯方法论的全网情报调研 skill：用户给出关注点（品牌/产品/舆情/竞品/事件），自动建立监测方案，
  采集公众号/小红书/微博/新闻/抖音/X/Reddit 提及与评论区，产出调研、预警与策略分析。
  数据源随话题动态匹配；每轮先盘点实采数据再生成分析逻辑，不套固定维度。
  支持 5 种场景：舆情监控、产品发布、行业调研、投资研究、金融单品追踪。
  调研完成后可切换本地实时看板（HTML，每轮自动更新）。
  无脚本、无服务端，由模型直接执行采集与分析，输出 markdown。
description_en: >
  A pure-methodology skill for web intelligence research. Given a focus topic (brand / product /
  public opinion / competitor / event), it builds a monitoring plan, collects mentions and
  comments from WeChat articles, Xiaohongshu, Weibo, news, Douyin, X, and Reddit, and produces
  research, alerts, and strategy reports. Data sources are matched dynamically per topic; each
  round inventories actual samples first, then derives analysis logic instead of forcing a fixed
  dimension set. Five scenario presets: public opinion monitoring, product launch, industry
  research, investment research, single-product financial tracking. After research, switch to an
  optional local live dashboard (self-contained HTML, refreshed each round). No scripts or
  server — the model executes collection and analysis directly and outputs markdown.
description: >
  纯方法论的全网情报调研 skill：用户给出关注点（品牌/产品/舆情/竞品/事件），自动建立监测方案，
  采集公众号/小红书/微博/新闻/抖音/X/Reddit 提及与评论区，产出调研、预警与策略分析。
  数据源随话题动态匹配；每轮先盘点实采数据再生成分析逻辑，不套固定维度。
  支持 5 种场景：舆情监控、产品发布、行业调研、投资研究、金融单品追踪。
  调研完成后可切换本地实时看板（HTML，每轮自动更新）。
  无脚本、无服务端，由模型直接执行采集与分析，输出 markdown。
---

# MYOU网络情报分析师

> 面向市场/公关与研究负责人的免费全网情报方法论：填入关注点 → 建监测 → 采集 → 分析 → 预警 → 策略。

本文件定义**核心流程与判断规则**。采集细则、报告模板、存储格式见 `references/`，需要时再读，不要预先全量加载。

| 参考文件 | 用途 | 何时读 |
|----------|------|--------|
| [references/data_sources.md](references/data_sources.md) | 渠道优先级、动态选源、降级链、平台要点、采集礼貌 | Phase 2 采集前 |
| [references/scenarios.md](references/scenarios.md) | 5 场景链路、关键词矩阵占位、默认频率档 | Phase 1 / 改方案时 |
| [references/templates.md](references/templates.md) | research.md 骨架、topic_id、状态机、去重、报告模板 | 初始化 / 写盘前 |
| [references/metrics.md](references/metrics.md) | 分层抽样权威标准、KMI、情绪/KOL、信号映射 | Phase 2 采样 / Phase 3 分析 |
| [references/dashboard.md](references/dashboard.md) | 本地看板：触发、模块表、data.js 富文案契约 | 开启或更新看板时 |
| [references/examples.md](references/examples.md) | 行业示例（可替换，非默认字段） | 填关键词矩阵时可选 |

## 核心原则

1. **问题发现导向**：目的是发现问题与机会，不是罗列数据
2. **文字主体**：所有结论必须有完整文字描述，图表仅辅助
3. **证据可追溯**：每条数据带来源、时间、采集方式
4. **增量不覆盖**：新数据追加写入 research.md，历史不可被覆盖
5. **演变优先**：关注时间变化，而非单点快照
6. **真实时间戳**：`timestamp` 使用实际采集时间
7. **评论区必采**：已启用的数据源必须采评论区并做平台级归纳
8. **标签全中文**：来源/情感/阶段/信号等展示标签使用中文
9. **空模块隐藏**：无数据的分析模块省略，不写空白章节
10. **不设固定套路**：8 维度只是候选池；先盘点实采数据，再生成本轮分析逻辑
11. **样本量透明**：量化指标必须标注样本量与采集范围；样本不足只做定性观察
12. **基准自校准**：第 1 轮建话题基线，之后以话题自身历史为比较基准
13. **源随话题走**：数据源按话题特征动态匹配，主源失败用备选源补齐
14. **不臆造数据**：缺口就标注缺口，禁止用旧数据或推断冒充新数据
15. **边界清晰**：本 skill 只产出结构化 markdown；推送/推送通道由宿主工具负责
16. **礼貌采集与停机**：遵守平台节奏，单源失败有限重试；主源与备选均不可用则结束本轮并报告缺口，禁止空转凑数
17. **隐私与合规**：不写入手机号/身份证/住址等个人敏感信息；不对普通用户做人肉拼图或煽动网暴；仅基于公开信息分析

## 话题生命周期

数据根目录：`~/.local/share/data-research/`，每话题一目录。

| 动作 | 何时 | 做什么 |
|------|------|--------|
| **新建** | 用户给出新关注点且目录下无相近话题 | 生成 `topic_id` → 建目录与 research.md → 出监测方案 |
| **复用确认** | 新关注点与已有话题高度相似（同品牌/同产品/同事件） | 先列出候选，询问「续跑已有话题还是新建」；禁止静默双开 |
| **续跑 resume** | 新会话继续盯已有话题 | 读 front matter + 话题摘要 + 近 2–3 轮演变 → 按 frequency 进入 Phase 2 |
| **列出 list** | 用户问「在盯什么」或 resume 前 | 扫描根目录，输出 `topic_id · 场景 · 状态 · rounds · updated_at` |
| **暂停 pause** | 用户要求或观测窗结束 | `status: paused`；停止 loop；不删数据 |
| **归档 archive** | 话题结束或长期不再更新 | `status: archived`；只读，不自动采集 |

`status` 取值：`active` | `paused` | `archived`。仅 `active` 执行定时采集。

### topic_id 规范

- 小写字母/数字/短横线，长度 4–40
- 优先英文或拼音 slug（如 `brand-x-launch`、`mifinance-su7`）；避免纯日期
- 与目录下已有 id 冲突 → 追加短后缀（`-2`），并告知用户
- 创建后写入 front matter，全程不变

### 恢复话题（新会话必做）

用户说「继续 / resume / 上次那个话题」时：

1. 执行 list，展示候选
2. 用户确认或通过关键词匹配唯一话题
3. 只读摘要与近几轮演变（禁止全文吸入历史数据条目）
4. 汇报一句：当前阶段、最近关键变化、活跃预警、建议下轮重点
5. 再进入采集

## 场景预设

从用户自然语言识别场景，默认「舆情监控」。匹配优先级从高到低：

| 优先级 | 场景 | 触发词示例 | 核心目标 |
|--------|------|------------|----------|
| 1 | 金融单品追踪 | 单品追踪、热品、交易机会、标的、股价背离、交付量 | 单品势能 + 热品排名 + 交易信号 |
| 2 | 投资研究 | 股票、投资、估值、财报、业绩、市值、持仓 | 机会与风险判断 |
| 3 | 产品发布 | 发布、新品、上市、首发、预售、交付、开售 | 发布期口碑与传播 |
| 4 | 行业调研 | 行业、赛道、市场、趋势、产业、政策 | 趋势与竞争格局 |
| 5 | 舆情监控（默认） | 舆情、口碑、评价、争议、品牌、事件 | 风险预警与叙事 |

各场景的分析链路、关键词矩阵占位、默认频率档、实体字段见
[references/scenarios.md](references/scenarios.md)。

## 工作流程

### Phase 1 — 话题解析

从自然语言提取：**话题 / 场景 / 关注维度 / 实体元信息**。按场景生成 5 层关键词矩阵：

| 层级 | 类型 | 作用 |
|------|------|------|
| 1 | 品牌/产品/公司词 | 主体识别 |
| 2 | 配置/场景/业务词 | 讨论焦点 |
| 3 | 竞品/对标词 | 对比热度 |
| 4 | 决策/评价/金融词 | 购买或交易意图 |
| 5 | KOL/催化剂词 | 节点与扩散 |

规则：按话题复杂度给出约 5–15 组关键词，并说明每层用途；冷门话题不硬凑。

初始化时必须：
1. **先 list 检查**是否已有相近话题，有则确认复用或明确新建理由
2. 生成并展示「监测方案」（见产品化流程），请用户确认或修改
3. 按 `topic_id` 规范创建目录与 `research.md`（骨架见 [templates.md](references/templates.md)）
4. 写入该话题的「调研方法论」章节（可被用户覆写，后续以其为准）

### Phase 2 — 数据采集

每轮完整执行；细则与降级链见 [data_sources.md](references/data_sources.md)。

**采集渠道优先级**（环境内可用者优先）：

1. 具备页面控制能力的浏览器工具（复用已登录会话）——小红书/抖音/微博/X 等需登录态平台
2. websearch —— 新闻、公众号、研报、公开网页
3. webfetch —— 指定 URL 全文

**每轮必做步骤**：

1. **Web 搜索**：关键词检索；首轮限最近 7 天，后续限自上轮采集时间之后
2. **平台深度采集**：按「数据源动态选择」执行，提取列表、互动、标签、传播路径
3. **评论区分层采样**（每个已启用数据源）：
   - 取互动量 Top 5–10 内容
   - 每条内容抽 15–30 条评论（优先高赞 + 最新 + 争议/分歧）
   - 输出该平台评论区总结（模板见 templates.md）
   - 报告中写明：`样本量 n=…，来源 … 条内容`；n < 30 时只做定性描述
4. **深度页面**（按需）：高价值 URL 抓全文，提取论点与数据
5. **KOL 画像**（按需）：参与话题的头部/中腰部账号定位、态度、合作风险

每条数据写入时标注 `collection_method`。采集后立即追加写入 research.md（格式见 templates.md）。

**失败与停机线**：

- 单平台：同一入口失败最多重试 1 次（间隔由宿主决定）；再失败 → 标注缺口，切备选源
- 本轮若 **全部计划源均无法取得有效样本** → 立即结束采集，在报告写明「本轮未取得新数据」及原因，**禁止用旧数据或空洞段落凑一轮**
- 单平台单轮浏览/打开详情页建议不超过约 30 次；超出优先保证已采样本的分析质量
- 细则见 [data_sources.md](references/data_sources.md)「礼貌采集与停机」

### Phase 3 — 数据分析（每轮专属）

**Step 1 盘点（必做）**

| 盘点项 | 内容 |
|--------|------|
| 各平台采集量 | 条数、内容类型、互动量级、时间范围 |
| 关键内容 | 爆款/争议、新账号、新叙事、传播路径 |
| 数据缺口 | 未采到的平台/维度及原因 |
| 覆盖结论 | 本轮能回答什么、不能回答什么 |

**Step 2 生成本轮分析逻辑（必做）**

基于盘点回答：能答什么 / 不能答什么 / 下轮补什么。然后：

- 从 8 维度候选池选用有证据支撑的维度，可自定义；禁止凑数
- 报告开头写明本轮分析逻辑（维度、理由、基准、样本量）
- 默认输出「相比上轮变了什么」；首轮建立话题基线
- 第 2 轮起阈值用话题自身历史，预警以「环比突变 + 绝对水平」双条件触发

**8 维度候选池**：搜索热度 · 内容生态 · 评论区情绪 · KOL 画像 · 竞品对比 · 话题发酵 · 风险评估 · 预测研判

KMI 公式与阈值、演变节点与信号结构见 [metrics.md](references/metrics.md)。

### Phase 4 — 预测性研判

预测类型与数量由本轮分析逻辑决定（可为 0–N）。第 2 轮起默认至少输出「下一轮最可能的变化」。

每条预测必须包含：**结论 + 触发条件 + 跟踪指标**。禁止空泛预测。

### Phase 5 — 持续循环

采集 → 分析 → 沉淀 → 等待 → 再采集。

默认观测频率**由监测方案的 `frequency` 字段驱动**；各场景默认档与产品发布 D-30…D+30 参考表见
[references/scenarios.md](references/scenarios.md)。

- 长期舆情：daily 或 weekly
- 金融：事件驱动 + 盘后/盘前
- 行业：weekly；重大政策/融资事件日 daily

定时采集可用宿主的 loop / cron 类工具，例如：`/loop 30m 继续采集话题「XXX」`。

## 产品化流程

### 监测方案（初始化时展示，确认后执行）

```
监测方案
- 话题 / 场景 / 目标
- 5 层关键词矩阵（可编辑）
- 数据源范围（按话题勾选）
- 采集频率 frequency
- 预警规则（类型 + 阈值 + 级别 + SLA）
- 报告模板（一页摘要 / 标准 / 周报）
- 本地看板 dashboard（on/off，默认 off；首轮报告后会再询问一次）
```

### 预警输出

每轮默认输出预警段。触发时按级别（红/橙/黄/蓝）给出结构化告警：

```json
{
  "severity": "red|orange|yellow|blue",
  "type": "volume_spike|negative_surge|new_keywords|kol_negative|competitor_shift|emotion_turn",
  "indicator": "指标变化 + 样本量",
  "evidence": ["URL 或内容引用"],
  "sla": "2 小时响应|当天|1-3 天|持续观察",
  "recommended_action": "具体建议"
}
```

> 边界：skill 只产出上述 markdown/JSON 文本。是否推送企业微信/飞书/邮件，由宿主或用户自行配置，不在本 skill 职责内。

### 报告三层

| 层 | 给谁 | 内容 | 时机 |
|----|------|------|------|
| 一页摘要 | 决策者 | 态势 / 关键变化 / 预警 / 建议 | 每轮默认 |
| 标准报告 | 执行 | 见 [templates.md](references/templates.md) 章节表 | 每轮 |
| 危机快报 | 危机时 | 事件 / 证据 / 影响 / 处置 / 口径建议 | 红/橙预警 |
| 周报（可选） | 决策/执行 | 相对上周变化、指标快照、预警与下周关注 | `frequency: weekly` 或用户要求 |

**交付去向**：

- 默认：完整报告在对话中输出
- 可选落盘：`{topic-id}/reports/R{n}-{date}.md`（标准报告）；危机快报另存 `reports/crisis-{date}.md`。`reports/` 默认不入 git
- research.md **只沉淀**数据条目/演变/信号/预警/预案，不重复粘贴整份报告正文（可存一页摘要要点）

### 危机处置闭环

红/橙预警 → 危机快报 → 处置建议 → 预案写入「## 预案库」→ 约 72h 后补采复盘并更新预案。

### 竞品对标

本品 vs 竞品声量份额（SoV）、情感与 KOL 指标横向对比。无竞品数据时标注「仅内部基准」。

### 本地实时看板

- **首轮完整报告输出后必须询问一次**是否开启本地看板；监测方案里也可预选 `dashboard: on`
- 开启后在 `{topic-id}/dashboard/` **按本话题动态生成** `index.html` + `data.js`（场景模块、监控词、竞品名、解读与预测全部贴合本任务；禁止套用固定成品页）
- 每轮：写完 research.md → 重写 data.js（含长文案）→ 模块有变则重新生成 index.html
- 看板必须以**文字解读 + 预测（结论/触发/跟踪）**为主，数字为辅；不替代标准报告，也不是采集触发器
- 契约与模块表见 [references/dashboard.md](references/dashboard.md)；`dashboard_template.html` 仅作生成骨架参考

## 数据存储

```
~/.local/share/data-research/{topic-id}/research.md
```

开启看板时另有：

```
~/.local/share/data-research/{topic-id}/dashboard/{index.html,data.js}
```

唯一存储文件。front matter + 调研方法论 + 数据说明 + 数据条目 + 演变 + 信号 + 预警记录 + 预案库。
（KMI 快照写在各轮「演变」节点内，不设独立章节。）
完整骨架、增量读写策略、内容去重规则、滚动归档见
[references/templates.md](references/templates.md)。

## 执行检查清单（每轮结束前）

- [ ] 已启用数据源均完成评论区分层采样，且报告写了样本量（`n=`）
- [ ] 每条数据有来源 / 时间 / `collection_method`
- [ ] 先盘点后分析，本轮分析逻辑已显式写出
- [ ] 量化指标均标注样本量；缺口已标注，无臆造
- [ ] 首轮已建立话题基线；第 2 轮起「本轮变化」与上轮可对比
- [ ] 主源/备选失败已按停机线处理；无「空轮凑数」
- [ ] 未写入个人敏感信息（手机号/身份证/住址等）
- [ ] research.md 已按增量规则追加，历史未被覆盖
- [ ] 首轮完整报告后已询问是否开启本地看板；若 `dashboard: on`，已按本话题生成/更新看板，解读与预测齐全
- [ ] 无空模块；标签为中文

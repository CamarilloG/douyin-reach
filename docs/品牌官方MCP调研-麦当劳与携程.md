# 品牌官方 MCP 调研：麦当劳中国 / 携程，及国内现状

> 调研时间：2026-09-01　| 目的：搞清楚「品牌方自己开放 MCP 给 AI 调用」这条路现在长什么样，
> 有哪些可复用的设计范式，以及对 douyin-reach 有什么参考价值。

---

## 0. 结论速览

| 对象 | 是否官方标准 MCP | 面向谁 | 能不能真的下单 | 接入门槛 |
|------|-----------------|--------|---------------|----------|
| **麦当劳中国 MCP** | ✅ 是（`https://mcp.mcd.cn`，Streamable HTTP） | **个人用户**，中国大陆 | ✅ 能，但支付外置为 H5 链接 | 手机号登录 → 控制台一键激活 Token，免费 |
| **携程商旅 AI 开放平台** | ✅ 是（明确 MCP 协议） | **企业**（差旅管理员） | ❌ 主要是查询/推荐/合规，非下单闭环 | 企业身份 + 商务对接，分层收费 |
| **携程问道** | ❌ 否（自家 HTTP API / Skill 形态） | 开发者，需认证 | ❌ 攻略型信息，非实时库存 | 账号认证审核，有 QPS/配额 |
| **携程门票 / 同程机票火车票** | ✅ 以 MCP 形态挂在百度搜索开放平台 MCP 广场 | 百度生态内的 Agent | 视服务而定，以搜索/查询为主 | 走百度 MCP 广场 |

一句话：**麦当劳是目前国内「品牌官方 MCP」做得最完整、门槛最低、最值得抄作业的样本；携程不是一个 MCP，而是三条形态不同的线（企业向 MCP / 攻略 API / 渠道分发），并且它的 AI 网关实践比它的对外 MCP 更有工程参考价值。**

---

## 1. 麦当劳中国 MCP

### 1.1 时间线（官方版本日志）

| 日期 | 版本 | 内容 |
|------|------|------|
| 2025-12-09 | 1.0.0 | 首发：麦麦日历（活动日历）+ 麦麦省领券 |
| 2026-01-23 | 1.0.1 | 新增餐品营养信息；缩短接入 URL |
| 2026-02-13 | 1.0.2 | 新增**麦乐送点餐**与积分兑换券场景 |
| 2026-04-02 | 1.0.3 | 新增**到店取餐**与**企业团餐**场景，附近门店查询 |
| 2026-05-21 | 1.0.4 | 积分兑换实物商品、商城订单查询；支持**得来速(DT)**与全场景**预约下单** |

节奏很清楚：**先做只读的低风险能力（日历/营养/券），跑通之后才逐步放开写操作（领券 → 点餐 → 支付 → 实物兑换）**。这个"先读后写、逐场景放量"的顺序值得照抄。

### 1.2 接入方式

- 服务地址：`https://mcp.mcd.cn`
- 传输协议：**Streamable HTTP**（不是 stdio，不是 SSE-only）
- 鉴权：请求头 `Authorization: Bearer YOUR_MCP_TOKEN`
- 协议版本：仅支持 **MCP Version 2025-06-18 及之前**
- 限流：**600 次/分钟/Token**，超限返回 `429`；Token 无效/过期返回 `401`
- 地域：仅中国大陆（不含港澳台）

客户端配置：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": { "Authorization": "Bearer YOUR_MCP_TOKEN" }
    }
  }
}
```

**Token 获取**：`https://open.mcd.cn/mcp` → 手机号验证码登录 → 右上角「控制台」→ 点「激活」→ 同意服务协议 → 一键复制。免费，无需企业资质。

官方点名适配的客户端：Cherry Studio、Cursor、TRAE、Kiro、VSCode。官方还给了一份「推荐 LLM」清单（截至 2026-02-12）：qwen-plus / qwen3-max、Doubao-Seed-1.6、Kimi k2.5、GLM-5、gemini-3-flash-preview、DeepSeek-V3.2 —— 即**品牌方会自己测哪些模型能稳定选对工具，并把结果写进文档**，这本身就是个信号：工具设计要为「模型选得对」服务。

### 1.3 工具清单（官方 24 个）

> 注：社区项目（如 `cwyhkyochen-a11y/mcdonalds-mcp`）里说的「18 个工具」是早期版本快照，以官方 `M-China/mcd-mcp-server` 为准。

**点餐主链路（12 个）**

| Tool | 说明 |
|------|------|
| `list-nutrition-foods` | 餐品营养成分（能量/蛋白/脂肪/碳水/钠/钙），支持按热量配餐 |
| `delivery-query-addresses` | 查询用户已有配送地址 |
| `delivery-create-address` | 新增配送地址 |
| `delivery-query-stores` | 外送场景下查收货地址附近可配送门店 |
| `query-nearby-stores` | 查询指定地址附近餐厅 |
| `query-meal-assistance` | 企业团餐场景的助餐服务 |
| `query-store-coupons` | 当前门店可用券 |
| `query-meals` | 当前门店在售菜单（分类/餐品编码/标签） |
| `query-meal-detail` | 餐品详情（套餐组成、默认选择） |
| `calculate-price` | 算价：商品金额 + 配送费 + 优惠 + 应付总价 |
| `create-order` | 创建订单，返回订单详情与**支付链接** |
| `query-order` | 订单状态/内容/配送信息 |

**优惠券（4 个）**：`campaign-calendar`（营销活动日历）、`available-coupons`（麦麦省可领券列表）、`auto-bind-coupons`（**一键领取全部可领券**）、`query-my-coupons`（我的券包）

**积分商城（7 个）**：`query-my-account`（积分余额/冻结/将过期）、`mall-points-products`、`mall-product-detail`、`mall-create-order`（兑餐品券）、`mall-create-order-physical`（兑实物，含收货地址与库存扣减）、`mall-order-list`、`mall-order-detail`

**通用（1 个）**：`now-time-info` —— 给 LLM 喂当前时间。**这是个很实用的小设计**：大模型不知道"今天"，日历/预约/有效期类工具全靠它兜底。

### 1.4 值得抄的设计点

1. **交易闭环做到「下单」为止，支付外置。** `create-order` 返回的是
   `orderId` / `payId` / `payH5Url`（`https://m.mcd.cn/mcp/scanToPay?orderId=...`），
   AI 不碰钱，最终由人在 H5 上完成支付。**把不可逆的资金动作留给人类点击**，
   这是目前品牌 MCP 最主流的安全边界划法。
2. **Token 即会员身份。** 文档反复强调"Token 代表会员身份，严禁分享"——
   鉴权同时解决了「是谁」和「用谁的券/积分/地址」，不需要额外的用户体系。
3. **工具描述里写清"何时使用"。** 例如 `create-order` 的描述直接写：
   *当用户说"帮我下单 xxx 商品"、"确认下单"时使用*。这是给模型的路由提示，
   不是给人看的 API 文档。
4. **不允许模型凭空捏造关键实体。** 社区实测踩坑记录：门店信息**必须**从
   `delivery-query-addresses` / 门店查询工具拿，不能自己编 `storeCode`；
   `calculate-price` 与 `create-order` 参数结构一致，先算价再下单。
5. **限流 + 明确错误码**（600/min，401/429）代替复杂风控，对个人用户足够。
6. **条款兜底**：仅限个人非商业用途；禁止商业售卖、付费分发、引流变现、
   暗示官方背书；禁止黑灰产用途。**能力放开，靠协议约束用途。**

### 1.5 快速验证方式

拿到 Token 后最小闭环：`now-time-info`（连通性）→ `campaign-calendar`（只读）→
`available-coupons` → `auto-bind-coupons`（第一个写操作）→ `query-my-coupons` 验证结果。
下单链路建议先 `calculate-price` 反复确认，再 `create-order`。

---

## 2. 携程：三条线，形态各不相同

### 2.1 携程商旅 AI 开放平台（2026-04-20 发布，**真·MCP**）

- 明确支持 MCP 协议，流程是：员工提问 → **企业自有 AI** 理解意图 → 调用商旅 MCP 工具 → 返回结构化结果 → 企业自有 AI 生成回复。
- 五大能力类别：
  1. 基础信息：天气、汇率、通用差旅政策、区域转 ID
  2. 实时资源推荐：酒店 / 火车 / 机票
  3. 核心查询：酒店深度信息、差标、航班火车信息、签证政策、车站模糊查询
  4. 行程规划：多城市多日行程自动化规划
  5. 差旅管理：数据明细查询、合规监控
- **分层开放**：标准层（低成本验证 AI 价值）/ 高级层（更丰富数据 + 深度系统集成）/ 定制层（共创）。
- 入口：`openapi.ctripbiz.com/#/advertise/mcp`，需**企业身份 + 商务对接**，技术文档不公开。

对比麦当劳：**麦当劳是 C 端普惠（一键激活、免费、能下单）；携程商旅是 B 端商务合作（要谈、要签、要分层）。** 这是两种完全不同的开放哲学。

### 2.2 携程问道（C 端 AI 助手的对外接口，**不是标准 MCP**）

- 携程问道是携程 2023-07 推出的 AI 旅行助手（攻略 + 榜单）。
- 对外开放形态是**自家 HTTP API**（`externalcallback.ctrip.com`）+ Skill 封装，
  通过 `WENDAO_API_KEY` 环境变量鉴权，**不是标准 MCP**。
- 定位是**攻略型**：酒店/机票/景点的信息查询，返回攻略层信息，**非实时库存价确**，
  不涉及支付与下单闭环。
- 门槛：需在携程开放平台完成企业/个人认证并审核（约 1–3 工作日），有 QPS / 配额限制；
  接入还需要 Node.js v18+ 跑脚本。

第三方实测对比（携程问道 vs RollingGo）的结论：**RollingGo 走标准 MCP + 交易闭环
（搜索→锁房→下单→订单查询→盯价，个人可零成本接入）；携程问道适合做攻略型助手，
不适合做交易型 Agent。** 这份对比来自第三方（且带有明显的推荐倾向），数字层面
（如"200 万+酒店"）建议只当参考，但**"协议标准 + 是否交易闭环 + 接入门槛"这三个维度
的判断框架是对的**。

### 2.3 渠道分发：携程门票 MCP 上百度 MCP 广场（2025-08-20）

百度搜索开放平台接入了携程门票、同程机票和火车票等 MCP。百度 MCP 广场已收录 **2.2 万+**
MCP Server。也就是说，**携程的 C 端能力是以「挂到别人的 MCP 广场」的方式对 Agent 开放的，
而不是自建一个像 `mcp.mcd.cn` 那样的公开入口。**

### 2.4 最有工程价值的一块：携程的 AI 网关实践

携程内部用 AI 网关（基于 Higress）统一治理大模型流量，其中有一段直接对应"**存量 HTTP API
如何规模化变成 MCP**"：

- **转换方案**：把 OpenAPI 契约喂给大模型，自动生成基本可用的工具描述；再对后端响应
  做**格式化**，保证模型读得懂。大幅降低人工转换成本。
- **鉴权**：调用方用 Bearer Token，每个 Token 关联一个 consumer，需申请审批；
  后端服务凭证统一存在网关，调用方无感。
- **SSE 支持**：因 SSE 请求/响应分离，网关做会话管理——生成 SessionID，
  在 Redis 监听 Channel，把响应流式推回客户端。
- **限流**：支持 TPM / QPM / 并发数三种阈值，Redis + Lua 原子计数。
- **可观测**：Prometheus → Grafana 监控；日志 FileBeat → Kafka → ClickHouse → Kibana。
- **踩过的坑**：各家大模型接口差异适配；存量 API 工具化的规模化；
  **工具数量过多导致大模型选择困难**。

最后一条是普遍问题：**工具不是越多越好，24 个（麦当劳）已经接近单 Server 的舒适上限。**

---

## 3. 横向：国内「官方 MCP」现状

| 主体 | 形态 | 备注 |
|------|------|------|
| **高德地图** | 官方 MCP Server（2025-03 首发，后发布 2.0） | 12 类核心数据源：位置、POI 搜索、路径规划、天气等；2.0 打通 MCP 与高德 App 唤起 |
| **支付宝** | 「支付 MCP Server」，国内首个支付场景 MCP | 支持移动端/网页端支付、查支付状态、发起退款；首发于魔搭 MCP 广场、支付宝百宝箱、开放平台 |
| **麦当劳中国** | 官方 MCP Server | 见上，**餐饮品牌里最早、最完整** |
| **携程 / 同程** | 企业向 MCP + 渠道分发 | 见上 |
| **字节 / 火山引擎** | MCP Market + 方舟 + Trae 全链路 | 抖音生态能力以火山引擎为出口；**抖音本身没有面向个人的官方 MCP** |
| **百度** | 搜索开放平台 MCP 广场（2.2 万+）、千帆企业级 MCP | 渠道方角色 |
| **阿里 / 魔搭** | MCP 广场 1400+ 服务，含在线实验场 | 分发 + 托管 |

趋势判断：**"每个品牌都需要一个网站 → 需要一个 App → 现在开始需要一个 MCP Server"**。
在 Agent 时代，「能被 AI 调用」正在变成新的 SEO / 分发入口。支付宝把**支付**做成 MCP、
高德把**唤起 App** 做成 MCP，说明大厂在争夺的是「Agent 调用链里的那个必经节点」。

---

## 4. 共性设计范式（可直接复用的 8 条）

1. **远程托管 + Streamable HTTP + Bearer Token**，已经是国内品牌 MCP 的事实标准；不要再做 stdio-only。
2. **Token 绑定真实账号身份**，一次鉴权解决身份与数据归属。
3. **能力按「先只读、后写入」灰度放开**，写操作按业务场景逐个上线。
4. **不可逆动作（支付/实名/提现）外置给人类**，MCP 只到"生成待支付订单"为止。
5. **工具描述面向模型写，包含"何时使用"的触发语**，而不是面向人的 API 文档。
6. **关键实体禁止模型编造**，必须由前置工具返回（门店码、地址 ID、商品编码）。
7. **限流 + 明确错误码（401/429）** 作为第一道风控，简单有效。
8. **用服务条款划定用途边界**（禁商业转售、禁引流变现、禁黑灰产），能力开放但责任清晰。

---

## 5. 对 douyin-reach 的启示

### 5.1 抖音侧：短期内没有"官方 MCP"这条捷径

搜索确认：**抖音没有面向个人开发者的官方 MCP Server**。市面上叫 `douyin-mcp-server` 的
全是社区项目（无水印视频链接提取、文案提取、数据分析等），字节的官方口径是走
火山引擎 MCP Market / 方舟 / 巨量引擎的企业生态。
**结论：我们基于 Playwright + CDP 的自动化路线短期内不可替代**，但要意识到方向性风险——
一旦平台提供官方 Agent 接口，逆向自动化的合规空间会被进一步压缩。

### 5.2 可以照抄到本项目的做法

| 麦当劳/携程的做法 | 落到 douyin-reach |
|-------------------|-------------------|
| 支付外置为 H5，人类点确认 | **私信发送前的人工确认**已经有了（名单审核 → 确认发送），保持住，不要为了"自动化程度"去掉它 |
| 600 次/分钟限流 + 明确错误码 | 对应 `data/settings.json` 里的发送间隔 / 日上限 / 任务上限；建议**把限流也做成显式错误码与提示**，而不是静默等待 |
| 先只读、后写入的能力灰度 | 采集（读）与私信（写）已经分离，继续保持"写操作必须过审核"的结构 |
| 工具描述写"何时使用" | 如果 `src/backend/filter/ai_provider.py` 走 function calling，工具描述要写触发语而非字段说明 |
| 响应数据格式化后再喂模型 | AI 筛选环节：评论/用户数据要先裁剪格式化再进 prompt，别把原始 DOM/JSON 甩给模型 |
| 工具太多模型选不准 | 若未来暴露工具，控制在 20 个以内并按场景分组 |

### 5.3 一个可选方向：把 douyin-reach 自己封装成本地 MCP Server

现有后端能力（`src/backend/api/real.py` 已有任务/采集/筛选/发送的完整方法）几乎可以
一对一映射成 MCP 工具，让用户在 Claude / Cherry Studio 里用自然语言驱动：

- 只读：`list-tasks`、`get-task-detail`、`query-collected-users`、`get-send-history`、`now-time-info`
- 低风险写：`create-task`、`update-task-rules`、`run-filter`、`export-csv`
- 高风险写：`send-dm` —— **建议不暴露，或仅暴露 `prepare-send`（生成待发送名单 + 确认链接），
  真正发送仍走 GUI 人工确认**，完全对齐麦当劳"支付外置"的边界划法。

代价很小（后端方法已存在，加一层 MCP adapter），收益是把工具从"GUI 应用"变成
"可被任意 Agent 编排的能力"。**但注意：麦当劳条款里明令禁止的"引流变现"类用途，
恰恰是我们这个工具的敏感区**——若对外分发 MCP，务必在文档里写清合规边界与使用者责任。

---

## 6. 参考链接

**麦当劳**
- 官方文档站：https://open.mcd.cn/mcp/doc ｜ Token 申请：https://open.mcd.cn/mcp
- 官方仓库（接入指南 + 完整工具文档）：https://github.com/M-China/mcd-mcp-server
- 社区实测项目：https://github.com/cwyhkyochen-a11y/mcdonalds-mcp
- 第三方分析报告：https://temp.jaylab.io/mcdonalds-mcp-skill-analysis-report

**携程**
- 携程商旅 AI 开放平台：https://ct.ctrip.com/thinktanks/235566117077549 ｜ 申请入口：https://openapi.ctripbiz.com/#/advertise/mcp
- 携程 AI 网关落地实践：https://ziyou.framer.website/blog/ctrip-s-practical-implementation-of-ai-gateway
- 携程问道 Skill 接入文档（第三方整理）：https://cloud.tencent.com/developer/article/2660097
- 旅行 Agent MCP 能力对比（第三方，含倾向性）：https://mcp.csdn.net/6a3e45cd662f9a54cb84bfdc.html
- 百度搜索开放平台接入携程/同程 MCP：https://www.ebrun.com/ebrungo/zb/592981.shtml

**生态**
- 高德 MCP Server：https://lbs.amap.com/api/mcp-server/summary
- 支付宝支付 MCP Server：https://www.qbitai.com/2025/04/273734.html
- 魔搭 MCP 广场：https://www.modelscope.cn/mcp
- 火山引擎 MCP（抖音生态出口）：https://developer.volcengine.com/articles/7509436621935411219

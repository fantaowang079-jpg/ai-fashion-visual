# 衣镜 TryOn Replica —— shop-tryon-skill 复刻版

把 `wzj177/shop-tryon-skill` 的虚拟试衣操作，重构成一个**独立、可干跑、可扩展**的 Python CLI：

```
服装图 / 文字描述
  -> 服装理解（可选）
  -> 模特推荐（45 个内置模特 / 用户上传）
  -> 试穿生成（默认百炼 qwen-image 图像编辑；可选 Seedream / aitryon-plus）
  -> AI 换装（指令换色/换款/加外套，或按服装图换衣）
  -> 多角度扩展
  -> 展示视频

Web 工作台：
  换装 / 试衣 / 智能穿搭（LLM 从内置衣橱选品）
  -> 历史记录 / Lookbook ZIP 导出
```

参考项目是一个 Agent Skill（SKILL.md + 一组互相调用的脚本）；本复刻版保留它的核心操作与提示词，但把流程收敛成一个命令行工具和清晰的 Provider 层，方便后续接入主项目（FastAPI + React 工作台）。

## 1. 能力

| 能力 | 命令 | 说明 |
|---|---|---|
| 查看配置 | `python cli.py config` | 只显示是否配置，不打印密钥 |
| 模特库 | `python cli.py models list` | 45 个内置模特，按女/男/童分组 |
| 模特推荐 | `python cli.py models recommend "JK制服"` | 按服装描述匹配性别、年龄段、风格 |
| 服装分析 | `python cli.py analyze garment.jpg --json` | qwen-vl 输出结构化服装信息 |
| 试穿 | `python cli.py run --garment g.jpg --part top` | 默认百炼 qwen-image 图像编辑；可切 Seedream / aitryon |
| AI 换装 | `python cli.py restyle --image p.jpg --instruction "换成米色针织开衫"` | qwen-image 指令编辑；也可 `--garment` 按服装图换衣 |
| 多角度 | `python cli.py angles --garment g.jpg --model m.jpg --preset ecommerce` | 正面/侧面/背面等预设 |
| 生视频 | `python cli.py video --image result.jpg` | Seedance 图生视频，9:16 |
| Web 工作台 | `python app.py` → `http://127.0.0.1:8000` | 换装 / 试衣 / 智能穿搭 / 图生视频 / 历史 五页签 |
| 智能穿搭 | 工作台「智能穿搭」页签 | LLM 从内置衣橱选品，输出 3 套结构化方案 |
| 图生视频 | 工作台「图生视频」页签 | 百炼万相 `wan2.5-i2v-preview`，5/10 秒、480P/720P/1080P |
| Lookbook | 结果页「导出 Lookbook」/ 历史卡片 | ZIP：主图 3:4 + 详情图 1:1 + 文案 + 参数 + 成本 |
| 余额 / 额度 | 顶栏「余额 / 额度」 | 阿里云 BSS 查真实余额；未配置 AccessKey 时显示引导、本地成本与最近额度错误 |
| 干跑 | 上述命令加 `--dry-run` | 不调用 API，只打印解析结果和 prompt |

## 2. 目录结构

```
replica/
├─ cli.py                 # 命令行入口
├─ app.py                 # FastAPI Web 工作台（上传/换装/任务查询）
├─ web/                   # 单页前端（原生 HTML/CSS/JS，无需构建）
├─ config.py              # .env 加载与 Settings
├─ providers/
│  ├─ ark.py              # 火山方舟：Seedream 生图 / Seedance 视频
│  ├─ dashscope.py        # 百炼：AI 换装 / 编辑式试衣 / aitryon / qwen-vl
│  └─ base.py             # 统一结果与异常
├─ core/
│  ├─ model_library.py    # 模特库读取、展示、推荐
│  ├─ prompts.py          # 分析/试穿/换装/多角度/视频提示词
│  ├─ session.py          # session 目录、分阶段保存、JSONL 日志
│  └─ pipeline.py         # 试穿、换装、多角度、视频编排
├─ assets/
│  ├─ models.json         # 45 个模特元数据
│  └─ models/*.png        # 模特参考图
├─ tests/test_core.py     # 不依赖网络的单元测试
├─ .env.example
└─ requirements.txt
```

## 3. 快速开始

要求：Python 3.10+（本机 3.12 已验证）。

### 一键启动（Windows）

双击：

```
E:\AI服饰视觉项目\replica\launch_workbench.bat
```

脚本会自动检查 Python、依赖和 8000 端口，然后启动服务；浏览器打开 `http://127.0.0.1:8000`。

> 不要命名为 `start.bat`：部分机器 PATH 里有同名 Redis 脚本，会优先执行它。

### 手动启动

```bash
cd E:\AI服饰视觉项目\replica
python -m pip install -r requirements.txt   # 首次运行
python app.py
```

首次使用或换电脑时，再按需准备：

```bash
# 1. 可选：虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 2. 配置 Key
copy .env.example .env
# 编辑 .env，至少填写 DASHSCOPE_API_KEY（百炼）
#
# 重要：DASHSCOPE_API_KEY 必须是百炼控制台「API-KEY 管理」创建的 sk- 字符串，
#       不是 RAM 的 AccessKey ID/Secret（LTAI...）。两者用途不同，混用会 401。

# 3. 检查配置
python cli.py config

# 4. 看模特库
python cli.py models list
```

### 3.0 阿里云百炼账号准备（只走百炼时）

1. 直接打开 API-Key 页面（华北2·北京）：
   `https://bailian.console.aliyun.com/cn-beijing/?tab=model#/api-key`
2. 首次进入会弹服务协议，勾选同意即可开通（开通免费）。
3. 点「创建我的 API-Key」→ 归属业务空间用默认 → 确定。
4. 立即复制 `sk-...`（完整 Key 只显示一次，丢了只能重建）。
5. 在 `replica/.env` 填 `DASHSCOPE_API_KEY=sk-...`。
6. 费用：默认 `qwen-image-3.0` 图像编辑约 **0.50 元/张**（估算）；若改用 AI 试衣 Plus 也约 0.50 元/张。新账号通常有免费额度（以控制台为准）。

> 注意：`LTAI...` 是 RAM AccessKey，不是百炼 API Key，不能调模型。

#### 3.0.1 常见报错排查

| 报错 | 原因 | 处理 |
|---|---|---|
| `AllocationQuota.FreeTierOnly` / 免费额度耗尽 | 账号开了「仅使用免费额度」，或免费额度用完 | 充值后在百炼控制台关闭「仅使用免费额度」；AI 试衣 Plus 约 0.50 元/张 |
| `Model not exist`（仅 `TRYON_ENGINE=aitryon`） | 当前业务空间未开通 AI 试衣，或用了标准域名但模型在业务空间下 | 切到华北2（北京）→ 模型广场搜「AI 试衣」并开通；或改回 `TRYON_ENGINE=edit` 使用 qwen-image |
| `InvalidApiKey` | 用了 AccessKey、跨地域 Key，或 Key 与 Base URL 不匹配 | 用北京地域、默认业务空间创建的 `sk-` Key |
| `Throttling.RateQuota` | 触发限流 | 降低并发，隔几秒重试 |

业务空间专属地址示例：

```ini
DASHSCOPE_BASE_URL=https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
DASHSCOPE_NATIVE_BASE_URL=https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com/api/v1
```

### 3.1 先干跑（不需要 Key）

```bash
# 只有服装图：推荐模特 + 组装 prompt
python cli.py run --garment "C:\path\garment.jpg" --part top --dry-run

# 只有描述：展示将如何生成服装图、选模特
python cli.py run --desc "米色针织开衫，通勤风" --part top --dry-run

# 看多角度计划
python cli.py angles --garment g.jpg --model m.jpg --preset ecommerce,detail --dry-run
```

干跑会打印：使用的方法、模特、参考图、完整 prompt、缺失的 Key，不会产生费用。

### 3.2 真实生成

```bash
# A. 提示词图生图（Seedream，参考项目默认路径）
python cli.py run --garment g.jpg --model m.jpg --part top --variants 2

# B. 百炼编辑式试衣（默认 TRYON_ENGINE=edit，使用 qwen-image）
python cli.py run --garment g.jpg --model m.jpg --part one_piece --method qwen

# C. 只有文字描述：先生成服装平铺图，再试穿
python cli.py run --desc "黑色JK制服，白色水手领，百褶裙" --part one_piece

# D. 上下装套装
python cli.py run --garment top.jpg --bottom-garment skirt.jpg --part full

# E. 多角度
python cli.py angles --garment g.jpg --model m.jpg --preset ecommerce --part one_piece

# F. 视频（先用 angles 多出几张图效果更好）
python cli.py video --image output/task_xxx/step3_tryon/xxx.png --duration 5 --ratio 9:16

# G. 多图视频（最多 4 张，自动用 LITE 模型）
python cli.py video --images a.jpg b.jpg c.jpg --prompt "同一套服装的场景切换展示"

# H. AI 换装：指令换色/换款/加外套（保留脸、姿势、背景）
python cli.py restyle --image 模特.jpg --instruction "把上装换成米白色宽松针织开衫"
python cli.py restyle --image 模特.jpg --instruction "换成米色针织开衫" --instruction "加一件同色系外套"

# I. AI 换衣：按目标服装图换装，服装图作为参考图2
python cli.py restyle --image 模特.jpg --garment 白衬衫.jpg --part top

# J. 批量：每条指令出 3 张候选
python cli.py restyle --image 模特.jpg --instruction "换成黑色西装外套" --count 3
```

> 换装默认走百炼 `qwen-image-3.0`（同步接口，约 10–40 秒/张）；模型不存在时自动降级到 `qwen-image-2.1-pro` / `qwen-image-2.0`，可用 `QWEN_IMAGE_EDIT_MODEL` / `QWEN_IMAGE_EDIT_FALLBACKS` 覆盖。指令只描述服装变化，不要写「换背景」，否则会与保护前缀冲突。

### 3.3 Web 工作台

```bash
cd E:\AI服饰视觉项目\replica
python app.py
# 浏览器打开 http://127.0.0.1:8000
```

页面能力：

**AI 换装页签**

- 点击或拖拽上传人物图（≤10MB），可选上传目标服装图；
- **内置模特库**：点「从内置模特库选择」，45 个模特按女/男/童筛选，选中后自动作为人物图；
- 快捷指令 + 自由输入，选择部位 / 数量 / 尺寸；
- **模型路由**：自动（主模型 + 失败降级）或手动指定 `qwen-image-3.0 / 2.1-pro / 2.0`；
- **费用预估**：按模型单价 × 数量实时显示预计费用。

**虚拟试衣页签**

- 上传人物图 + 服装平铺图，整套模式再传下装图；
- **内置模特库**：人物图可直接从 45 个内置模特中选择，不必自己上传；
- 生成方式：自动 / 百炼图像编辑（`qwen-image-3.0`）/ Seedream 多参考图（未配置方舟 Key 时自动禁用）；
- 可填服装描述，会写入 Prompt 帮助模型理解款式；
- 默认走 `qwen-image` 图像编辑试衣；若配置 `TRYON_ENGINE=aitryon` 且专用模型不可用，会自动兜底到图像编辑并标注；
- 费用按实际使用模型 × 数量预估。

**余额 / 额度（默认隐藏）**

> 当前入口默认不显示。需要时在 `.env` 把 `BALANCE_UI_ENABLED` 设为 `1` 并重启，即可恢复顶栏按钮；后端接口和代码保留。

- 顶栏点击「余额 / 额度」打开弹窗；
- 配置阿里云 AccessKey 后，通过 BSS OpenAPI `QueryAccountBalance` 显示可用余额、现金余额、信控额度；
- **可在弹窗内直接填写 AccessKey 并保存检测**，Secret 只保存在本机 `.env`，接口不回显；
- 支持更换/清除 AccessKey；未配置时保留本地估算成本（来自成本台账）与最近一次额度错误；
- `sk-` 百炼 API Key **没有余额接口**，不能直接查余额；
- 查询需要 RAM 用户只读权限 `AliyunBSSReadOnlyAccess`；
- 配置项（`.env`）：`ALIYUN_ACCESS_KEY_ID`、`ALIYUN_ACCESS_KEY_SECRET`。

**通用**

- 「仅预览 Prompt」勾选后不调用 API，适合演示彩排；
- 结果页带 **Before/After 拖拽对比**、下载、原图查看；
- **SSE 实时进度**：任务状态变化即时推送，断线自动回退到轮询；
- **成本台账**：每次生成记录任务类型、模型、张数、单价、金额、耗时，页面显示累计成本；
- 任务在后台串行执行；刷新页面会自动恢复进行中的任务；
- **任务持久化在 SQLite**：`output/tasks.db`（事实来源），内存只做缓存；启动时自动把旧版 `output/web_tasks/*.json` 迁移进数据库；
- 任务同时保留 JSON 镜像，便于人工排查；
- 可用 `http://127.0.0.1:8000/?tab=tryon` 直接打开试衣页签；
- 成本记录在 `output/cost_ledger.jsonl`。

**历史记录页签**

- 汇总所有仍有图片的生成记录（换装 / 试衣），按时间倒序；
- 卡片展示缩略图、时间、摘要、模型、张数、估算费用、耗时；
- 缩略图在任务完成时预生成并缓存（`output/.thumbs/`），避免历史页加载多张 3MB+ 原图；
- **删除**：每张图右上角可单独删除；「删除整条」会移除该记录及全部图片；删除最后一张后记录自动消失；
- **导出 Lookbook**：每条记录可直接下载 ZIP；
- 删除只清理本地文件，已产生的费用仍保留在成本台账中；
- 可用 `http://127.0.0.1:8000/?tab=history` 直达。

**智能穿搭页签**

- 选择场合（通勤/约会/旅行/运动/正式）、季节、色系偏好，可填起点单品；
- LLM 只从 `assets/wardrobe.json`（22 件内置衣橱）中选品，禁止编造单品 ID；
- 输出 3 套结构化方案：单品清单、配色、推荐理由、搭配要点；
- 每套方案可「用作换装指令」直接带到换装页签，或复制搭配文案；
- LLM 不可用时自动回退规则模板，演示不中断；
- 可用 `http://127.0.0.1:8000/?tab=stylist` 直达。

**图生视频页签**

- 上传首帧图片（推荐用试衣/换装结果），填写提示词；
- 时长 5/10 秒，分辨率 480P/720P/1080P；
- 默认走百炼万相 `wan2.5-i2v-preview`；配置 `ARK_API_KEY` 后也可选 Seedance；
- 费用按秒估算：480P ¥0.3/秒、720P ¥0.6/秒、1080P ¥1/秒；
- 生成结果可在页面播放、下载，并进入历史记录；
- 可用 `http://127.0.0.1:8000/?tab=video` 直达。

> 如果遇到 `AllocationQuota.FreeTierOnly`，说明账号开启了「免费额度用完即停」且额度耗尽：到百炼控制台「模型用量 → 免费额度」关闭该开关（或充值）后即可生成。本项目已实测出片成功。

**Lookbook 导出**

- 结果页成功后出现「导出 Lookbook」按钮；历史卡片也有导出入口；
- ZIP 结构：
  ```
  lookbook_<task_id>/
    images/01_main_3x4.jpg      # 主图 3:4
    images/01_detail_1x1.jpg    # 详情图 1:1
    images/01_original.png      # 原图
    lookbook.md                 # 搭配文案、场景建议、Prompt、成本
    manifest.json               # 完整生成参数与图片清单
  ```
- 多张结果会依次生成 01/02/... 套图；
- 导出文件保存到 `output/lookbooks/`。

接口一览：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/config` | Provider 状态、可选模型、估算单价 |
| POST | `/api/upload` | 上传人物图 / 服装图 |
| POST | `/api/restyle` | 提交换装任务，`dry_run=true` 只返回 Prompt |
| POST | `/api/tryon` | 提交试衣任务（qwen-image / aitryon / Seedream），支持干跑 |
| GET | `/api/tasks/{id}` | 查询任务 |
| GET | `/api/tasks/{id}/events` | SSE 实时进度 |
| GET | `/api/costs` | 成本台账汇总 |
| GET | `/api/history` | 生成历史（含缩略图地址） |
| DELETE | `/api/history/{id}` | 删除整条记录及全部图片 |
| DELETE | `/api/history/{id}/images/{index}` | 删除单张图片 |
| GET | `/api/lookbook/{id}` | 导出 Lookbook ZIP |
| POST | `/api/stylist` | 智能穿搭：生成 3 套方案 |
| POST | `/api/video` | 图生视频：首帧 + 提示词，支持干跑 |
| GET | `/api/models` | 内置模特库（45 个，含图片地址） |
| GET | `/api/models/{id}/image` | 模特参考图 |
| GET | `/api/balance` | 账户余额（需 AccessKey）+ 本地成本 + 最近额度错误 |
| POST | `/api/balance/config` | 保存 AccessKey 到本机 `.env`（不回显 Secret） |
| DELETE | `/api/balance/config` | 清除本机 AccessKey |
| GET | `/thumb/{relpath}` | 按需生成缩略图（缓存到 `output/.thumbs/`） |
| GET | `/files/{relpath}` | 读取生成结果 |

> 单 worker 串行执行，避免并发触发百炼限流；图片按张、视频按秒计费。单价为估算值，可用 `QWEN_IMAGE_EDIT_PRICES` / `WAN_VIDEO_PRICES` 覆盖，实际以控制台账单为准。

## 4. 输出结构

```
output/
├─ .current_session                 # 24h 内复用同一个 session
├─ .thumbs/                         # 历史页缩略图缓存（可随时删除重建）
├─ tasks.db                         # SQLite 任务持久化（事实来源）
├─ web_tasks/                       # 任务 JSON 镜像 / 旧版兼容
├─ lookbooks/                       # 导出的 Lookbook ZIP
├─ cost_ledger.jsonl                # 成本台账（每次生成一条）
└─ task_YYYYMMDD_HHMMSS/
   ├─ step1_garment/                # 由描述生成的服装图
   ├─ step2_model/                 # 预留：生成的模特图
   ├─ step3_tryon/                 # 试穿结果、多角度图
   ├─ step4_variants/              # 预留：变体
   ├─ step5_video/                 # 视频
   ├─ step6_restyle/               # AI 换装结果
   └─ session_log.jsonl            # 每次生成的元数据日志
```

Web 上传的原始素材保存在 `replica/uploads/`（已加入 `.gitignore`）。

- 所有结果立刻下载到本地，避免第三方 URL 过期。
- `--new-session` 强制新建目录；否则 24 小时内复用。
- `--output-dir` 可覆盖根目录（也可在 `.env` 里设 `TRYON_OUTPUT_DIR`）。

## 5. 两种试穿方式怎么选

| | Seedream 提示词图生图 | 百炼编辑式试衣（qwen-image） |
|---|---|---|
| 原理 | 参考图 + 强约束 prompt，让模型「照着画」 | 图像编辑模型按人物图 + 服装图重绘 |
| 服装保真 | 中高，复杂图案可能走样 | 中高，靠参考图与指令还原细节 |
| 人物控制 | 强（参考图锁定脸和姿势） | 强（保护前缀锁定脸/姿势/背景） |
| 类目 | 任意（上/下/连体/套装） | 任意（上/下/连体/套装），鞋包配饰也可尝试 |
| 速度 | 约 10–30 秒/张 | 约 30–90 秒/张 |
| 依赖 | `ARK_API_KEY` | `DASHSCOPE_API_KEY` |

`--method auto`：配置了 Ark 走 Seedream；只配置百炼则走 qwen-image。演示时建议两条都跑一遍做对比，这正是主项目「多模型路由」的素材。

> 若账号已开通专用试衣模型，可设 `TRYON_ENGINE=aitryon`、`TRYON_MODEL=aitryon-plus`，服装细节保真度更高；否则保持默认 `edit` 即可。

### 5.1 试衣 vs 换装怎么选

| | `run`（虚拟试衣） | `restyle`（AI 换装） |
|---|---|---|
| 输入 | 人物图 + 服装白底图 | 人物图 + 文字指令 / 目标服装图 |
| 原理 | 专用 try-on 模型把服装合成到人物 | 图像编辑模型按指令局部改服装 |
| 强项 | 服装细节还原度最高，适合新品上新 | 保留原场景与姿势，适合改色、改款、加外套 |
| 风险 | 对人物图要求严格 | 指令过宽时可能改动脸/背景 |
| 输出 | `step3_tryon/` | `step6_restyle/` |

推荐链路：**新服装 → `run` 试衣；已上身图 → `restyle` 改款/出多色**。

## 6. 模型与 API

| 用途 | 默认模型 | 环境变量 | 官方入口 |
|---|---|---|---|
| 生图 | `doubao-seedream-5-0-260128` | `ARK_IMAGE_MODEL` | 火山方舟控制台 |
| 视频（单图） | `doubao-seedance-1-5-pro-251215` | `ARK_VIDEO_MODEL_PRO` | 火山方舟控制台 |
| 视频（多参考图） | `doubao-seedance-1-0-lite-i2v-250428` | `ARK_VIDEO_MODEL_LITE` | 火山方舟控制台 |
| 试衣（默认） | `qwen-image-3.0`（图像编辑引擎） | `TRYON_MODEL` + `TRYON_ENGINE=edit` | 阿里云百炼 |
| 专用试衣（可选） | `aitryon-plus`（账号需开通） | `TRYON_ENGINE=aitryon` + `TRYON_MODEL` | 阿里云百炼 |
| 换装 | `qwen-image-3.0` | `QWEN_IMAGE_EDIT_MODEL` | 阿里云百炼 |
| 换装备选 | `qwen-image-2.1-pro` / `qwen-image-2.0` | `QWEN_IMAGE_EDIT_FALLBACKS` | 阿里云百炼 |
| 换装单价（估算） | 0.50 / 0.30 / 0.20 元/张 | `QWEN_IMAGE_EDIT_PRICES` | 以控制台账单为准 |
| 服装解析 | `aitryon-parsing` | 固定 | 阿里云百炼 |
| 服装分析 | `qwen-vl-max` | `QWEN_VL_MODEL` | 阿里云百炼 |
| 智能穿搭 | `qwen-plus`（账号不可用时换文本模型） | `STYLIST_MODEL` | 百炼 / 兼容平台 |
| 图生视频 | `wan2.5-i2v-preview` | `WAN_VIDEO_MODEL` | 阿里云百炼 |
| 视频单价（估算） | 480P 0.3 / 720P 0.6 / 1080P 1.0 元/秒 | `WAN_VIDEO_PRICES` | 以控制台账单为准 |

> 模型 ID / 价格会变，以控制台实际可用模型为准。参考项目里的 ID 已写成默认值，但上线前请核对。

## 7. 与参考项目的差异

保留：
- 服装分析提示词与 JSON 字段
- 45 个内置模特及推荐规则
- 试穿部位锁定提示词、多角度预设、视频全身锁定提示词
- session 分阶段目录与 JSONL 日志

改进：
- Provider 抽象：Seedream 与百炼图像编辑统一入口，便于加新供应商
- 干跑模式：没 Key 也能验证完整流程与 prompt
- 真正的 base64 降级：本地图片无需 OSS 也能送给两家 API
- 错误分层：配置错误、网络错误、任务失败分别提示
- 单测覆盖核心逻辑，不依赖网络
- **新增 AI 换装（参考项目没有）**：指令换装 + 参考服装图换衣，模型不存在时自动降级

未复刻（按需再加）：
- 即梦（Jimeng）客户端：需要单独签名，且参考项目已注明「有参考图不锁定人物」
- OSS 图床：当前用 base64，生产环境建议加 OSS/对象存储
- rembg 去背景：可选依赖，后续接入预处理模块
- 交互式菜单：CLI 改为显式参数，更适合自动化和后续 Web 化
- Claude 生成变体 prompt：改为内置模板，避免额外依赖；主项目里由 LLM 网关承担

## 8. 测试

```bash
python -m unittest discover -s tests -v
```

测试覆盖（73 项）：模特库与推荐规则、提示词、Session、干跑试穿/换装/多角度/视频、参数校验、成本估算与台账、衣橱与穿搭兜底、SQLite 任务存储与迁移、BSS 余额签名构造，以及 Web 接口（内置模特库与图片、上传校验、素材读取、换装/试衣/视频干跑、模型校验、SSE、成本汇总、余额检测、AccessKey 保存/清除、历史记录、单张/整条删除、缩略图、Lookbook ZIP、智能穿搭、任务 404、路径穿越防护）。

## 9. 许可与致谢

本项目参考并复刻了 [wzj177/shop-tryon-skill](https://github.com/wzj177/shop-tryon-skill)（MIT License）。

- **参考范围**：提示词模板、内置模特库（`assets/models.json` 与 45 张模特图）、Session 目录约定、试衣/多角度/视频流程
- **本项目新增**：Provider 抽象、统一配置、干跑模式、错误处理、单元测试、独立 CLI、Web 工作台、AI 换装、智能穿搭、图生视频、Lookbook、SQLite 任务持久化等

原项目 MIT 许可证全文：

```text
MIT License

Copyright (c) 2026 🍡

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

> 再分发本项目时，请保留上述版权与许可声明。

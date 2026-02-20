## Context

EvoClip 视频生成系统是面向电商内容团队的自动化带货视频生产工具。当前团队需 2–4 小时人工完成一条 1–3 分钟的带货视频，成本高、质量不稳定。

系统包含六个核心能力（`video-analysis`、`copy-generation`、`voice-synthesis`、`video-render`、`quality-evaluation`、`skill-optimization`），通过主 Agent 编排，所有 Skill 以 MCP Server 形式暴露。

---

## Tech Stack

### 后端技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| **语言** | Python 3.11+ | 主要开发语言 |
| **Web 框架** | FastAPI | 高性能异步 Web 框架，支持 OpenAPI 文档自动生成 |
| **MCP 协议** | mcp (Python SDK) | Model Context Protocol，Skill 间通信协议 |
| **ORM** | SQLAlchemy 2.0 | 异步 ORM，支持 PostgreSQL |
| **数据库连接池** | asyncpg | PostgreSQL 异步驱动 |
| **对象存储** | MinIO (minio-py) | S3 兼容对象存储客户端 |
| **缓存/消息** | Redis (redis-py) | 任务队列、缓存、Pub/Sub |
| **向量数据库** | ChromaDB | 本地向量存储，支持语义检索 |
| **视频处理** | FFmpeg (ffmpeg-python) | 视频剪辑、合成、转码 |
| **进程管理** | supervisord | 多进程管理，自动重启 |

### 前端技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| **语言** | TypeScript 5.x | 类型安全的 JavaScript 超集 |
| **框架** | Vue 3 | 组合式 API，响应式 UI |
| **构建工具** | Vite 5.x | 快速开发服务器，HMR |
| **路由** | Vue Router 4 | SPA 路由管理 |
| **HTTP 客户端** | Axios | HTTP 请求封装 |
| **工具库** | @vueuse/core | Vue 组合式工具函数 |
| **样式** | TailwindCSS + Headless UI | 原子化 CSS + 无样式组件库，高度自定义 |

### 外部服务 API

| 服务 | 提供商 | 用途 |
|------|--------|------|
| **视觉大模型** | 阿里云 Qwen2-VL | 视频帧场景分析、对象识别 |
| **语音识别** | 阿里云 Paraformer | 素材语音转文字，带时间戳 |
| **LLM** | DeepSeek / OpenAI GPT-4 | 文案生成、优化建议生成 |
| **TTS** | OpenAI TTS / 火山引擎 | 文案语音合成 |
| **向量嵌入** | 阿里云 Qwen Embedding | 诊断问题向量化，经验检索 |

### 基础设施

| 组件 | 技术 | 说明 |
|------|------|------|
| **数据库** | PostgreSQL 15+ | 任务元数据、版本历史 |
| **对象存储** | MinIO | 视频、音频、中间文件存储 |
| **缓存** | Redis 7.x | 任务队列、会话、SSE 事件 |
| **容器化** | Docker + docker-compose | 阶段 2 部署方案 |
| **反向代理** | Nginx | 前端静态文件、API 代理 |

### 技术架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端层 (Vue 3)                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ 上传组件 │  │ 进度组件 │  │ 预览组件 │  │ 下载组件 │        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
│       │             │             │             │               │
│       └─────────────┴──────┬──────┴─────────────┘               │
│                            │ SSE / REST API                     │
└────────────────────────────┼────────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────┐
│                     API 网关层 (FastAPI)                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ /tasks   │  │ /events  │  │ /download│                      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                      │
│       │             │             │                              │
└───────┼─────────────┼─────────────┼──────────────────────────────┘
        │             │             │
        ▼             ▼             ▼
┌───────────────────────────────────────────────────────────────┐
│                    主 Agent 编排层                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│  │ Main Agent │  │ Evaluator  │  │ Optimizer  │               │
│  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘               │
│         │               │               │                      │
└─────────┼───────────────┼───────────────┼──────────────────────┘
          │ MCP Tool Call │               │
          ▼               ▼               ▼
┌───────────────────────────────────────────────────────────────┐
│                    MCP Skill Server 层                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐              │
│  │video-analysis│ │copy-gen    │ │voice-synth │              │
│  └─────────────┘ └─────────────┘ └─────────────┘              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐              │
│  │video-render │ │quality-eval │ │skill-optim  │              │
│  └─────────────┘ └─────────────┘ └─────────────┘              │
└───────────────────────────────────────────────────────────────┘
          │               │               │
          ▼               ▼               ▼
┌───────────────────────────────────────────────────────────────┐
│                      存储层                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │  MinIO   │  │PostgreSQL│  │  Redis   │  │ ChromaDB │      │
│  │ 对象存储 │  │ 关系数据库│  │ 缓存/队列│  │ 向量存储 │      │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │
└───────────────────────────────────────────────────────────────┘
          │               │               │
          ▼               ▼               ▼
┌───────────────────────────────────────────────────────────────┐
│                    外部服务 API 层                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Qwen2-VL │  │Paraformer│  │   LLM    │  │   TTS    │      │
│  │ 视觉分析 │  │ 语音识别 │  │ 文案生成 │  │ 语音合成 │      │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │
└───────────────────────────────────────────────────────────────┘
```

---

**约束：**
- 采用标准 MCP Tool Call 协议，Skill 之间不直接调用
- MinIO 存储视频文件、音频文件及中间产物；PostgreSQL 存储任务元数据；Redis 用于任务队列和缓存；ChromaDB 用于向量检索
- 每个 Skill 独立进程，可单独扩展/替换

---

## Goals / Non-Goals

**Goals:**
- 用户上传素材视频 + 填写商品描述后，全自动输出最终 MP4
- 支持多种视觉大模型和 TTS 服务的可插拔接入（统一适配器接口）
- Evaluator + Optimizer Agent 形成自进化闭环，逐步提升生成质量
- 每个 Skill 以独立 MCP Server 进程运行，主 Agent 通过标准 Tool Call 编排

**Non-Goals:**
- 不提供实时流式视频预览（输出为离线 MP4 文件）
- 不支持多用户并发隔离（初版单租户，无权限系统）
- 不实现自定义视频模板编辑器（风格由 Skill Prompt 控制）
- 不自研 TTS / 视觉大模型，仅做 API 封装

---

## Decisions

### 决策 1：Skill 以 MCP Server 协议暴露，而非直接 Python 库调用

**选择**：每个 Skill（VisualSkill、CopySkill、VoiceSkill、RenderSkill）作为独立 MCP Server 进程运行，主 Agent 通过 `mcp.tool_call()` 调用。

**原因**：
- MCP 协议天然支持跨进程/跨语言的 Skill 替换，未来可用 Node.js 或 Go 实现 Skill 而不影响主 Agent
- 独立进程隔离崩溃域；RenderSkill 调用 FFmpeg 时的内存/CPU 峰值不影响其他 Skill
- 与 Evaluator/Optimizer Agent 的编排方式统一，降低心智负担

**备选方案**：直接 Python 函数调用（更简单，但耦合高，无法独立替换 Skill 实现）

---

### 决策 2：场景映射以 `scene_id` 作为全链路唯一键

**选择**：`video-analysis` 输出的每个场景分配全局唯一 `scene_id`（格式：`s_{index}`），后续 `copy-generation`、`voice-synthesis`、`video-render` 全部以 `scene_id` 作为数据关联键。

**原因**：
- 保证文案句、音频片段、视频片段的三元组绑定关系在整个管道中可追溯
- `timeline.json` 按 `scene_id` 索引，便于 Evaluator Agent 做逐段质量诊断
- 支持未来局部重新生成（只重跑某个 `scene_id` 对应的环节，而非重跑全流程）

**备选方案**：以时间戳区间关联（实现简单，但重新生成时时间戳会漂移，不稳定）

---

### 决策 3：四层存储架构（MinIO + PostgreSQL + Redis + ChromaDB）

**选择**：
- **MinIO**：对象存储，存储视频文件、音频文件、中间产物（关键帧 JPEG、临时 MP4、最终输出等）
- **PostgreSQL**：关系型数据库，存储任务元数据（任务 ID、输入路径、各 Skill 参数版本、诊断结果摘要）
- **Redis**：缓存与消息队列，用于任务队列、临时数据、会话状态、Skill 执行进度
- **ChromaDB**：向量数据库，存储 Skill Prompt 模板的历史版本及诊断向量，供 Optimizer Agent 检索相似案例

**原因**：
- MinIO 提供 S3 兼容接口，支持分布式部署和水平扩展，适合大文件存储
- PostgreSQL 提供企业级数据管理能力，支持复杂查询和事务
- Redis 提供高性能缓存和任务队列能力，支持断点续跑和实时状态推送
- Optimizer Agent 需要语义检索"与当前诊断问题相似的历史优化经验"，结构化查询无法满足

**备选方案**：本地文件系统 + SQLite 单机存储（无法扩展，不支持分布式部署）

---

### 决策 4：FastAPI 作为后端 HTTP 网关，与 MCP Server 分离部署

**选择**：前端通过 FastAPI REST API 上传文件、查询任务状态、下载结果；FastAPI 不直接编排 Skill，而是委托给主 Agent 进程。

**原因**：
- FastAPI 负责 HTTP 层的文件上传/流式状态推送（SSE），主 Agent 专注编排逻辑
- 两者职责分离，便于后续替换前端协议（如 WebSocket）而不影响 Agent 逻辑

**备选方案**：主 Agent 直接暴露 HTTP 接口（逻辑混杂，不易测试）

---

### 决策 5：集成阿里 Paraformer 进行素材语音识别

**选择**：在 `video-analysis` Skill 中集成阿里 Paraformer API，提取素材视频中的语音内容，生成带时间戳的转录文本，作为文案生成的参考上下文。

**原因**：
- 素材视频可能包含原始配音或解说，提取这些内容可以帮助生成更贴合素材的文案
- 带时间戳的转录文本与场景时间轴分段对齐，实现精准的上下文关联
- Paraformer 中文语音识别效果好，电商场景优化

**备选方案**：OpenAI Whisper API（英文场景更优）

---

### 决策 6：素材标签注入到文案生成 Prompt

**选择**：`copy-generation` Skill 在调用 LLM 时，将每个场景的 `description`（场景描述）、`objects`（对象列表）和 `transcription`（语音识别结果）注入 Prompt 上下文。

**原因**：
- 确保生成的文案与素材内容高度匹配，避免"文不对题"
- `objects` 字段帮助 LLM 识别场景中的关键商品或元素，生成更精准的卖点描述
- `transcription` 字段（如有）提供素材原始语音内容参考，保持文案风格一致性

**备选方案**：仅使用商品描述生成文案（忽略素材内容，可能导致文案与画面不匹配）

---

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 外部 API 限速/超时导致流程中断 | 每个 Skill 实现指数退避重试（最多 3 次）；主 Agent 记录断点，支持从失败 Skill 重续 |
| FFmpeg 合成时内存溢出（大素材视频） | RenderSkill 按场景分段合成，最后 concat 合并；限制单次处理素材不超过 500MB |
| TTS 音频时长与场景时长不匹配导致音画不同步 | `voice-synthesis` 返回精确 `duration_ms`；`video-render` 按音频时长裁剪视频片段（音频优先策略） |
| 向量数据库冷启动时无历史经验可检索 | Optimizer Agent 首次运行时使用内置的默认 Prompt 模板，不依赖检索结果 |
| Skill 进程崩溃导致主 Agent 无法感知 | MCP Server 健康检查心跳（30s interval）；主 Agent 超时后自动重启对应 Skill 进程 |
| Paraformer 语音识别失败或无语音内容 | 语音识别失败时返回 `transcription: null`，不中断流程；文案生成仅依赖视觉分析结果 |
| 素材标签注入导致 Prompt 过长 | 对 `description` 和 `transcription` 字段进行截断处理，保留关键信息；控制单场景上下文不超过 500 tokens |

---

## Project Structure

```
evoclip/
├── agent/                          # 主 Agent 编排器
│   ├── __init__.py
│   ├── main_agent.py              # 主 Agent 入口，编排全链路流程
│   ├── evaluator.py               # Evaluator Agent，调用 quality-evaluation
│   └── optimizer.py               # Optimizer Agent，调用 skill-optimization
│
├── skills/                         # MCP Skill Server 模块
│   ├── __init__.py
│   ├── video_analysis/            # video-analysis Skill
│   │   ├── __init__.py
│   │   ├── server.py              # MCP Server 入口
│   │   ├── frame_extractor.py     # 关键帧提取
│   │   ├── vision_adapter.py      # Qwen2-VL 适配器
│   │   └── speech_recognizer.py   # Paraformer 语音识别
│   │
│   ├── copy_generation/           # copy-generation Skill
│   │   ├── __init__.py
│   │   ├── server.py              # MCP Server 入口
│   │   └── prompt_builder.py      # LLM Prompt 构建
│   │
│   ├── voice_synthesis/           # voice-synthesis Skill
│   │   ├── __init__.py
│   │   ├── server.py              # MCP Server 入口
│   │   └── tts_adapter.py         # TTS 适配器（OpenAI/火山引擎）
│   │
│   ├── video_render/              # video-render Skill
│   │   ├── __init__.py
│   │   ├── server.py              # MCP Server 入口
│   │   └── ffmpeg_wrapper.py      # FFmpeg 封装
│   │
│   ├── quality_evaluation/        # quality-evaluation Skill
│   │   ├── __init__.py
│   │   ├── server.py              # MCP Server 入口
│   │   ├── sync_checker.py        # 音画同步检测
│   │   ├── visual_checker.py      # 黑屏/模糊帧检测
│   │   └── prohibited_checker.py  # 违禁词扫描
│   │
│   └── skill_optimization/        # skill-optimization Skill
│       ├── __init__.py
│       ├── server.py              # MCP Server 入口
│       └── memory_store.py        # ChromaDB 向量存储
│
├── api/                            # FastAPI 后端网关
│   ├── __init__.py
│   ├── main.py                    # FastAPI 应用入口
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── tasks.py               # 任务 CRUD 接口
│   │   └── events.py              # SSE 进度推送
│   └── schemas/
│       ├── __init__.py
│       └── task.py                # Pydantic 模型
│
├── web/                            # 前端 Web UI
│   ├── package.json               # Node.js 依赖
│   ├── vite.config.ts             # Vite 配置
│   ├── tsconfig.json              # TypeScript 配置
│   ├── tailwind.config.js         # TailwindCSS 配置
│   ├── postcss.config.js          # PostCSS 配置
│   ├── index.html                 # 入口 HTML
│   ├── src/
│   │   ├── main.ts               # 应用入口
│   │   ├── App.vue               # 根组件
│   │   ├── api/                  # API 客户端
│   │   │   ├── client.ts         # Axios 封装
│   │   │   └── tasks.ts          # 任务 API
│   │   ├── composables/          # Vue Composables
│   │   │   ├── useTask.ts        # 任务状态管理
│   │   │   └── useSSE.ts         # SSE 进度监听
│   │   ├── components/           # UI 组件（Headless UI + TailwindCSS）
│   │   │   ├── VideoUploader.vue # 视频上传组件
│   │   │   ├── TaskProgress.vue  # 任务进度组件
│   │   │   ├── VideoPreview.vue  # 视频预览组件
│   │   │   └── DownloadButton.vue# 下载按钮组件
│   │   ├── views/                # 页面视图
│   │   │   ├── HomeView.vue      # 首页（上传）
│   │   │   └── TaskView.vue      # 任务详情页
│   │   ├── router/               # 路由配置
│   │   │   └── index.ts
│   │   └── styles/               # 样式文件
│   │       └── main.css          # TailwindCSS 入口
│   └── public/                    # 静态资源
│       └── favicon.ico
│
├── store/                          # 存储层
│   ├── __init__.py
│   ├── database.py                # PostgreSQL 连接池
│   ├── models.py                  # SQLAlchemy ORM 模型
│   ├── minio_client.py            # MinIO 客户端封装
│   └── redis_client.py            # Redis 客户端封装
│
├── config/                         # 配置文件
│   ├── config.yaml                # 主配置文件
│   ├── prompts/                   # Skill Prompt 模板
│   │   ├── copy_generation.yaml
│   │   └── skill_optimization.yaml
│   └── dictionaries/              # 违禁词词典
│       └── prohibited_words.txt
│
├── tests/                          # 测试目录
│   ├── __init__.py
│   ├── test_video_analysis.py
│   ├── test_copy_generation.py
│   └── ...
│
├── scripts/                        # 运维脚本
│   ├── init_db.py                 # 数据库初始化
│   └── init_minio.py              # MinIO Bucket 初始化
│
├── supervisord.conf               # 进程管理配置
├── pyproject.toml                 # Python 项目配置
└── README.md                      # 项目说明
```

---

## Migration Plan

1. **阶段 1（本地单机）**：所有组件（FastAPI、主 Agent、各 MCP Skill Server）在同一机器上启动，使用 `supervisord` 管理进程；MinIO + PostgreSQL + Redis + ChromaDB 存储
2. **阶段 2（容器化）**：每个 Skill Server 打包为独立 Docker 镜像，通过 `docker-compose` 编排；共享 volume 存储中间文件
3. **回滚策略**：Skill 版本配置写入 PostgreSQL 版本表，Optimizer 更新失败时自动回滚到上一版本配置；任务级别的中间产物保留 7 天供手动回溯

---

## Open Questions

（所有问题已决策，转为下方 Decisions 记录）

---

## Resolved Decisions

### 决策 7：视觉大模型选用 Qwen2-VL

**选择**：优先使用 Qwen2-VL 作为视觉分析模型。

**原因**：
- 中文电商场景优化更好，对商品描述、场景理解更准确
- API 成本相对较低
- 支持本地部署（如有 GPU 资源可切换）

---

### 决策 8：ChromaDB 嵌入模型使用 OpenAI 兼容 API

**选择**：使用兼容 OpenAI 格式的 API（如 Qwen Embedding API）进行向量化。

**原因**：
- 本地环境不支持离线部署
- Qwen Embedding API 兼容 OpenAI 格式，切换成本低
- 中文语义理解效果更好

**配置示例**：
```yaml
embedding:
  provider: openai_compatible
  api_base: https://dashscope.aliyuncs.com/compatible-mode/v1
  model: text-embedding-v3
```

---

### 决策 9：违禁词库使用内置静态词典

**选择**：使用内置静态词典进行违禁词扫描，词典从配置文件加载。

**原因**：
- 简单可控，支持自定义词库
- 无外部 API 依赖，无额外费用
- 适合初版快速迭代

**词典格式**：每行一个词汇，UTF-8 编码的文本文件

---

### 决策 10：前端使用 SSE 实时进度推送

**选择**：通过 SSE（Server-Sent Events）实时推送 Skill 执行进度。

**原因**：
- 实时性好，用户体验佳
- Redis Pub/Sub 可直接支持后端事件分发
- 前端实现简单，浏览器原生支持 EventSource

**实现方案**：
- 后端：FastAPI SSE 端点 + Redis Pub/Sub
- 前端：EventSource 监听进度事件

---

### 决策 11：语音识别使用阿里 Paraformer API

**选择**：使用阿里 Paraformer API 进行素材语音识别。

**原因**：
- 中文语音识别效果好，电商场景优化
- API 成本相对较低
- 支持带时间戳的转录输出

**备选方案**：OpenAI Whisper API（英文场景更优）

---

### 决策 12：语音识别结果与场景时间轴分段对齐

**选择**：语音识别结果按场景时间轴分段，每个场景输出独立的 `transcription` 字段。

**原因**：
- 文案生成时可以精确引用对应场景的语音内容
- 避免"文不对题"，提升文案与画面的匹配度
- 支持局部重新生成时保留上下文

**实现方案**：
- 根据场景的 `start_ms`/`end_ms` 切分转录文本
- 每个场景的 `transcription` 包含该时间段内的语音内容

## 1. 项目基础结构

- [x] 1.1 初始化 Python 后端项目目录结构（`agent/`、`skills/`、`api/`、`store/`、`config/`、`tests/`、`scripts/`）并配置 `pyproject.toml`
- [x] 1.2 添加后端核心依赖：`fastapi`、`uvicorn`、`mcp`、`chromadb`、`ffmpeg-python`、`openai`、`sqlalchemy`、`minio`、`redis`、`dashscope`（阿里云 API）
- [x] 1.3 创建统一配置文件 `config/config.yaml`，定义视觉模型（Qwen2-VL）、语音识别（Paraformer）、TTS 服务、LLM、MinIO 连接、Redis 连接、违禁词词典路径、Embedding API 等可切换参数
- [x] 1.4 初始化 PostgreSQL 数据库表：`tasks`（任务元数据）、`skill_versions`（Skill 版本历史）
- [x] 1.5 初始化 MinIO Bucket：创建 `videos`（素材视频）、`audio`（音频文件）、`intermediate`（中间产物）、`output`（最终输出）四个 Bucket
- [x] 1.6 初始化 Redis 数据结构：配置任务队列 Key 前缀、会话过期时间、进度缓存 TTL、SSE 事件通道
- [x] 1.7 编写 `supervisord.conf`，管理主 Agent 进程和各 MCP Skill Server 进程的启动顺序
- [x] 1.8 初始化前端项目 `web/`，配置 Vue 3 + TypeScript + Vite 开发环境
- [x] 1.9 添加前端核心依赖：`vue`、`vue-router`、`axios`、`@vueuse/core`、`tailwindcss`、`@headlessui/vue`
- [x] 1.10 创建前端基础组件：`VideoUploader.vue`、`TaskProgress.vue`、`VideoPreview.vue`、`DownloadButton.vue`
- [x] 1.11 实现前端 API 客户端封装（`api/client.ts`、`api/tasks.ts`）
- [x] 1.12 实现前端 SSE 进度监听 Composable（`composables/useSSE.ts`）
- [x] 1.13 实现 `store/database.py`：PostgreSQL 异步连接池（asyncpg + SQLAlchemy）
- [x] 1.14 实现 `store/models.py`：SQLAlchemy ORM 模型定义（Task、SkillVersion 表）
- [x] 1.15 实现 `store/minio_client.py`：MinIO 客户端封装（Bucket 管理、文件上传/下载）
- [x] 1.16 实现 `store/redis_client.py`：Redis 客户端封装（任务队列、缓存、Pub/Sub）
- [x] 1.17 创建 `config/prompts/copy_generation.yaml`：文案生成 Prompt 模板
- [x] 1.18 创建 `config/prompts/skill_optimization.yaml`：优化建议 Prompt 模板
- [x] 1.19 创建 `config/dictionaries/prohibited_words.txt`：违禁词词典（每行一个词汇）

## 2. video-analysis Skill（MCP Server）

- [x] 2.1 创建 `skills/video_analysis/server.py`，注册为 MCP Server，暴露 `analyze_video` Tool
- [x] 2.2 实现视频文件校验逻辑：检查文件格式（MP4/MOV）和大小限制（≤ 500MB），返回对应错误码
- [x] 2.3 使用 `ffmpeg-python` 按 1fps 提取关键帧，存储至 MinIO `intermediate` Bucket
- [x] 2.4 实现 Qwen2-VL 视觉大模型适配器接口，调用阿里云 DashScope API
- [x] 2.5 实现场景合并算法：将相邻相似帧聚合为场景片段，分配 `scene_id`（`s_0`、`s_1`…）
- [x] 2.6 实现 API 指数退避重试（1s/2s/4s，最多 3 次），超时阈值 30s
- [x] 2.7 集成阿里 Paraformer API：调用语音识别服务，获取带时间戳的转录文本
- [x] 2.8 实现语音分段对齐：根据场景 `start_ms`/`end_ms` 切分转录文本，为每个场景生成独立的 `transcription` 字段
- [x] 2.9 处理无语音或识别失败场景：返回 `transcription: null`，不中断流程
- [x] 2.10 输出结构化 JSON：`[{scene_id, start_ms, end_ms, description, objects, transcription}]`，存储至 MinIO `intermediate` Bucket
- [x] 2.11 为 `analyze_video` 编写单元测试，覆盖正常场景、超大文件、格式错误、API 超时重试、语音识别失败

## 3. copy-generation Skill（MCP Server）

- [x] 3.1 创建 `skills/copy_generation/server.py`，暴露 `generate_copy` Tool
- [x] 3.2 实现输入校验：商品描述非空检查，场景列表长度 ≥ 1
- [x] 3.3 构建 LLM Prompt 模板，将场景描述（`description`）、对象列表（`objects`）和商品信息注入
- [x] 3.4 实现素材标签注入：将 `objects` 字段格式化注入 Prompt，引导生成与场景内容匹配的文案
- [x] 3.5 实现语音识别结果注入：若 `transcription` 非空，将其作为额外上下文注入 Prompt
- [x] 3.6 实现 `estimated_duration_s` 计算（按 3.5 字/秒估算，精度 0.1s）
- [x] 3.7 输出结构化 JSON：`[{sentence_id, scene_id, text, estimated_duration_s}]`，验证所有 `scene_id` 引用合法
- [x] 3.8 实现 LLM API 指数退避重试（最多 3 次），失败返回 `llm_api_unavailable`
- [x] 3.9 为 `generate_copy` 编写单元测试，覆盖正常生成、空描述、scene_id 非法引用、LLM 失败、素材标签注入

## 4. voice-synthesis Skill（MCP Server）

- [x] 4.1 创建 `skills/voice_synthesis/server.py`，暴露 `synthesize_voice` Tool
- [x] 4.2 实现 TTS 适配器接口，支持 OpenAI TTS 和火山引擎 TTS 两种后端（通过配置切换）
- [x] 4.3 逐句调用 TTS API，生成 `{sentence_id}.mp3` 文件并存储至 MinIO `audio` Bucket
- [x] 4.4 通过解析 MP3 文件头读取精确 `duration_ms`（精度 ±10ms）
- [x] 4.5 实现单句失败容错：三次重试全部失败时标记 `status: "failed"`，继续处理剩余句子
- [x] 4.6 输出结构化 JSON：`[{sentence_id, audio_path, duration_ms, status}]`
- [x] 4.7 为 `synthesize_voice` 编写单元测试，覆盖正常合成、空输入、磁盘写入失败、TTS 重试场景

## 5. video-render Skill（MCP Server）

- [x] 5.1 创建 `skills/video_render/server.py`，暴露 `render_video` Tool
- [x] 5.2 实现音频优先裁剪逻辑：以 `duration_ms` 为准裁剪对应视频片段（短则截断，长则循环/静帧补齐）
- [x] 5.3 使用 FFmpeg 对每个三元组执行 `cut + merge audio` 操作，生成分段中间文件
- [x] 5.4 使用 FFmpeg `concat` 拼接所有分段为最终 MP4，自动创建不存在的输出目录
- [x] 5.5 处理 `status: "failed"` 的音频条目：跳过对应场景，在 timeline 中标记 `skipped: true`
- [x] 5.6 输出 `timeline.json`：`[{scene_id, sentence_id, start_ms, end_ms, audio_path, subtitle_text, skipped}]`，验证 `start_ms` 单调递增
- [x] 5.7 为 `render_video` 编写单元测试，覆盖正常合成、音频时长不匹配、跳过场景、输出目录不存在

## 6. quality-evaluation Skill（MCP Server）

- [x] 6.1 创建 `skills/quality_evaluation/server.py`，暴露 `evaluate_quality` Tool
- [x] 6.2 实现音画同步检测：读取 `timeline.json`，计算每段音视频时长差，超过 200ms 记录 `sync_error`
- [x] 6.3 实现黑屏检测：按 1fps 采样，亮度均值 < 10 且连续超过 500ms 标记为 `black_screen`
- [x] 6.4 实现模糊帧检测：拉普拉斯方差 < 100 且连续超过 500ms 标记为 `blur`
- [x] 6.5 实现违禁词扫描：从配置文件加载词典，匹配所有 `subtitle_text`
- [x] 6.6 实现 `overall_score` 计算（满分 100，sync_error -10，visual_issue -15，prohibited_word -20，下限 0）
- [x] 6.7 输出 `diagnosis.json`：`{overall_score, sync_errors, visual_issues, prohibited_words, generated_at}`
- [x] 6.8 为 `evaluate_quality` 编写单元测试，覆盖全优情况、各类缺陷检测、文件不存在错误

## 7. skill-optimization Skill（MCP Server）

- [x] 7.1 创建 `skills/skill_optimization/server.py`，暴露 `optimize_skills` Tool
- [x] 7.2 初始化 ChromaDB 实例，配置 Qwen Embedding API（兼容 OpenAI 格式）
- [x] 7.3 实现诊断问题向量化与相似历史检索（余弦相似度 ≥ 0.75，最多返回 3 条）
- [x] 7.4 实现冷启动降级：ChromaDB 为空时，直接使用内置默认 Prompt 模板生成优化建议
- [x] 7.5 调用 LLM 生成优化建议 JSON：`[{skill, optimization_type, param_path, new_value, expected_improvement}]`
- [x] 7.6 实现 `overall_score == 100` 时短路返回空列表，不调用 LLM
- [x] 7.7 实现 Skill 配置文件写入与 PostgreSQL `skill_versions` 表记录；写入失败时从版本表回滚
- [x] 7.8 实现自动应用模式：`overall_score < 60` 时自动批量应用全部建议
- [x] 7.9 将本次诊断+优化结果写入 ChromaDB 向量文档
- [x] 7.10 为 `optimize_skills` 编写单元测试，覆盖冷启动、正常优化、满分短路、回滚场景

## 8. 主 Agent 编排器

- [x] 8.1 创建 `agent/main_agent.py`，通过 MCP Client 连接所有 Skill Server
- [x] 8.2 实现全链路编排：`video-analysis → copy-generation → voice-synthesis → video-render`
- [x] 8.3 实现断点续跑：记录每个 Skill 的执行状态到 PostgreSQL `tasks` 表，失败时从断点 Skill 重续
- [x] 8.4 实现 MCP Server 健康检查心跳（30s interval），超时后自动重启对应 Skill 进程
- [x] 8.5 集成 Evaluator Agent（调用 `quality-evaluation`）和 Optimizer Agent（调用 `skill-optimization`），形成自进化闭环

## 9. FastAPI 后端网关

- [x] 9.1 创建 `api/main.py`，实现 `POST /tasks` 接口（接受视频文件上传 + 商品描述）
- [x] 9.2 实现 `GET /tasks/{task_id}` 接口，返回任务状态和进度
- [x] 9.3 实现 `GET /tasks/{task_id}/download` 接口，从 MinIO 获取最终 MP4 文件流返回
- [x] 9.4 实现 SSE 端点 `GET /tasks/{task_id}/events`，通过 Redis Pub/Sub 推送 Skill 执行进度事件
- [x] 9.5 实现静态文件服务，支持前端 Vue 应用部署
- [x] 9.6 为接口编写集成测试，覆盖正常流程和错误响应格式

## 10. 前端 Web UI

- [x] 10.1 实现首页 `HomeView.vue`：视频上传表单 + 商品描述输入框
- [x] 10.2 实现任务详情页 `TaskView.vue`：进度展示 + 视频预览 + 下载按钮
- [x] 10.3 实现 `useSSE.ts` Composable：SSE 连接管理、事件解析、自动重连
- [x] 10.4 实现 `useTask.ts` Composable：任务状态管理、API 调用封装
- [x] 10.5 实现 `VideoUploader.vue`：拖拽上传、格式校验、进度条
- [x] 10.6 实现 `TaskProgress.vue`：Skill 执行步骤展示、实时状态更新
- [x] 10.7 实现 `VideoPreview.vue`：MP4 视频播放器组件
- [x] 10.8 实现 `DownloadButton.vue`：下载按钮、文件名生成
- [x] 10.9 配置前端路由：`/`（首页）、`/task/:id`（任务详情）
- [x] 10.10 前端构建与部署配置（Vite build、Nginx 配置）

## 11. 端到端验证

- [x] 11.1 准备测试素材：准备 ≤ 30s 的带货视频素材和商品描述文本
- [ ] 11.2 执行完整流程端到端测试，验证最终 MP4 和 `timeline.json` 正确生成
- [ ] 11.3 验证 `diagnosis.json` 输出的三项检测结果符合预期
- [ ] 11.4 触发 Optimizer Agent，验证 ChromaDB 写入和 PostgreSQL 版本记录正常
- [ ] 11.5 前端端到端测试：上传视频 → 查看进度 → 预览视频 → 下载文件
- [ ] 11.6 SSE 实时性测试：验证进度事件实时推送到前端
- [x] 11.7 编写 `README.md` 记录本地启动步骤（依赖安装、配置 API Key、supervisord 启动、前端启动）

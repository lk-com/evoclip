## Why

电商内容团队制作一条 1-3 分钟的带货视频需要人工撰写文案、录制配音、逐帧剪辑，平均耗时 2-4 小时，成本高且质量依赖个人经验无法稳定复制。本系统通过 Agent + MCP + Skill 架构，让用户只需上传视频素材并填写商品描述，即可全自动完成文案撰写、TTS 配音、素材剪辑与最终合成，并通过自进化闭环持续提升生成质量。

## What Changes

- 引入主 Agent 控制器，负责编排全链路生成流程
- 新增 VisualSkill：逐帧分析用户素材视频，输出带时间戳的场景列表 JSON
- 新增语音识别模块：集成阿里 Paraformer API，提取素材视频中的语音内容，作为文案生成参考
- 新增 CopySkill：基于场景列表、素材标签和商品信息，生成与场景一一对应的分句文案（每句绑定 scene_id）
- 新增 VoiceSkill：对每句文案调用 TTS 生成音频片段，返回精确时长
- 新增 RenderSkill：按 [文案句-音频-素材片段] 三元组顺序调用 FFmpeg 合成最终 MP4，并输出 timeline.json
- 新增 Evaluator Agent：读取 timeline.json，检查音画同步、黑屏/模糊帧、违禁词三项客观指标，生成诊断报告
- 新增 Optimizer Agent：读取诊断报告，更新对应 Skill 的 Prompt 模板或参数配置并写入 Memory Store
- 所有 Skill 通过 MCP Server 协议暴露，主 Agent 通过标准 Tool Call 调用

## Capabilities

### New Capabilities

- `video-analysis`: 接收用户上传至 MinIO 的素材视频文件，逐帧提取关键帧，调用 Qwen2-VL 分析每帧场景内容，同时使用 Paraformer API 提取语音内容并分段对齐，输出带起止时间戳的场景描述列表（`[{scene_id, start_ms, end_ms, description, objects, transcription}]`）
- `copy-generation`: 接收场景列表（含素材标签和语音识别结果）和商品描述文本，调用 LLM 生成与场景一一对应的分句文案，每句绑定 `scene_id`，输出结构化 JSON（`[{sentence_id, scene_id, text, estimated_duration_s}]`）
- `voice-synthesis`: 接收文案句子数组，逐句调用 TTS 服务生成 MP3 音频片段，返回每段音频文件路径及精确时长（`[{sentence_id, audio_path, duration_ms}]`）
- `video-render`: 接收场景映射、音频片段列表和素材视频，按三元组顺序调用 FFmpeg 剪切/拼接，输出最终 MP4 文件及 `timeline.json`（记录每段的起止时间戳、音频路径、字幕文本）
- `quality-evaluation`: 读取 `timeline.json` 和生成视频，执行三项客观检查：① 音画时间轴同步误差 ② 黑屏/模糊帧检测 ③ 文案违禁词扫描；输出结构化诊断报告（`diagnosis.json`）
- `skill-optimization`: 读取诊断报告和历史 Memory Store，生成针对问题 Skill 的参数/Prompt 优化建议，更新 Skill 版本配置并写入向量记忆，供下次生成时检索

### Modified Capabilities

（无现有能力需要修改）

## Impact

- **新增依赖**：FFmpeg（视频合成）、Qwen2-VL（视觉大模型）、阿里 Paraformer（语音识别）、TTS 服务 API（如 OpenAI TTS / 火山引擎）、LLM API（DeepSeek / GPT-4 等）、Qwen Embedding API（向量嵌入）
- **存储**：
  - **MinIO**：对象存储，存储视频文件、音频文件、中间产物（关键帧、临时 MP4 等）
  - **PostgreSQL**：关系型数据库，存储任务元数据和诊断历史
  - **Redis**：缓存，用于任务队列、临时数据、会话状态、SSE 事件分发
  - **ChromaDB**：向量数据库，存储 Skill Prompt 模板历史版本及诊断向量，用于经验检索
- **架构**：
  - **后端**：Python FastAPI + MCP Server（每个 Skill 独立进程）
  - **前端**：Web UI（上传、预览、下载、SSE 实时进度）
  - **进程管理**：supervisord 管理主 Agent 和各 Skill Server
- **外部 API 调用**：Qwen2-VL（视觉分析）、Paraformer（语音识别）、LLM（文案生成）、TTS（语音合成）、Qwen Embedding（向量嵌入）五类外部服务需要配置 API Key

## Tech Stack Summary

| 层级 | 技术选型 |
|------|----------|
| **前端** | Vue 3 + TypeScript + Vite + Vue Router + Axios + TailwindCSS + Headless UI |
| **后端** | Python 3.11+ + FastAPI + SQLAlchemy 2.0 + MCP SDK |
| **数据库** | PostgreSQL 15+ |
| **对象存储** | MinIO |
| **缓存/队列** | Redis 7.x |
| **向量存储** | ChromaDB |
| **视频处理** | FFmpeg |
| **进程管理** | supervisord |
| **容器化** | Docker + docker-compose（阶段 2） |
| **反向代理** | Nginx |

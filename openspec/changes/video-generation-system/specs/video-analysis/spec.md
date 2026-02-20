## ADDED Requirements

### Requirement: 接受素材视频并提取关键帧
系统 SHALL 接受用户上传至 MinIO 的素材视频文件（MP4/MOV，最大 500MB），按固定帧率（默认每秒 1 帧）提取关键帧图像，将关键帧 JPEG 文件存储至 MinIO `intermediate` Bucket 用于后续分析。

#### Scenario: 合法视频文件上传成功
- **WHEN** 用户提供一个 MinIO `videos` Bucket 中不超过 500MB 的 MP4 文件对象键
- **THEN** 系统 SHALL 成功从 MinIO 读取文件并提取关键帧序列，将关键帧存储至 `intermediate` Bucket，不报错

#### Scenario: 文件超过大小限制
- **WHEN** 用户提供的 MinIO 视频文件超过 500MB
- **THEN** 系统 SHALL 返回错误信息 `"video_too_large"`，并说明当前文件大小与限制值

#### Scenario: 不支持的文件格式
- **WHEN** 用户提供的 MinIO 对象非 MP4/MOV 格式
- **THEN** 系统 SHALL 返回错误信息 `"unsupported_format"`

---

### Requirement: 调用视觉大模型分析每帧场景内容
系统 SHALL 将提取的关键帧逐批发送至 Qwen2-VL 视觉大模型 API，获取每帧的场景描述、主要对象与情绪标签。

#### Scenario: 视觉模型返回有效描述
- **WHEN** 关键帧成功发送至视觉大模型 API
- **THEN** 系统 SHALL 收到包含场景描述文本和对象列表的响应，并继续处理

#### Scenario: 视觉模型 API 超时或限速
- **WHEN** 视觉大模型 API 在 30 秒内未返回响应，或返回 429 状态码
- **THEN** 系统 SHALL 以指数退避策略（1s、2s、4s）最多重试 3 次；全部失败后返回错误 `"vision_api_unavailable"`

---

### Requirement: 使用阿里 Paraformer 提取视频语音内容
系统 SHALL 使用阿里 Paraformer API 提取素材视频中的语音内容，生成带时间戳的转录文本，并根据场景时间轴分段对齐。

#### Scenario: 视频包含可识别语音
- **WHEN** 素材视频中包含清晰的语音内容
- **THEN** 系统 SHALL 输出转录文本及对应的时间戳区间，根据场景 `start_ms`/`end_ms` 切分后写入每个场景 JSON 的 `transcription` 字段

#### Scenario: 视频无语音或语音不可识别
- **WHEN** 素材视频中无语音内容，或语音质量过差无法识别
- **THEN** 系统 SHALL 将该场景的 `transcription` 字段设为 `null`，不报错

#### Scenario: Paraformer API 调用失败
- **WHEN** Paraformer API 超时（>60s）或返回错误
- **THEN** 系统 SHALL 以指数退避策略最多重试 2 次；全部失败后继续流程，所有场景的 `transcription` 字段为 `null`

---

### Requirement: 输出带时间戳的场景列表 JSON
系统 SHALL 将相邻的相似帧合并为场景片段，为每个场景分配全局唯一 `scene_id`（格式：`s_0`、`s_1` …），输出结构化 JSON 数组。

#### Scenario: 正常场景分割输出
- **WHEN** 所有关键帧分析完成
- **THEN** 系统 SHALL 输出 JSON 数组，每项包含 `scene_id`（字符串）、`start_ms`（整数毫秒）、`end_ms`（整数毫秒）、`description`（字符串）、`objects`（字符串数组）、`transcription`（字符串或 null），且 `start_ms < end_ms`

#### Scenario: 视频只有一个场景
- **WHEN** 整段视频内容高度一致，无明显场景切换
- **THEN** 系统 SHALL 输出包含单个场景条目的 JSON 数组（`scene_id: "s_0"`），覆盖完整视频时长

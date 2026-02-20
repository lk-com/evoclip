## ADDED Requirements

### Requirement: 逐句调用 TTS 服务生成音频片段
系统 SHALL 接受 `copy-generation` 输出的文案句子数组，逐句调用 TTS 服务（支持 OpenAI TTS 或火山引擎 TTS，通过配置切换），为每句文案生成独立的 MP3 音频文件，存储至 MinIO `audio` Bucket。

#### Scenario: 正常生成音频
- **WHEN** 接收到非空的文案句子数组（每句 `text` 非空）
- **THEN** 系统 SHALL 为每个 `sentence_id` 生成一个独立的 MP3 文件，存储至 MinIO `audio` Bucket，对象键格式为 `{task_id}/{sentence_id}.mp3`

#### Scenario: 文案数组为空
- **WHEN** 输入的文案句子数组长度为 0
- **THEN** 系统 SHALL 返回错误 `"empty_sentences"`，不调用 TTS API

---

### Requirement: 返回音频文件路径和精确时长
系统 SHALL 在输出中为每条记录提供 `sentence_id`、`audio_path`（MinIO 对象键，格式 `audio/{task_id}/{sentence_id}.mp3`）、`duration_ms`（整数毫秒，通过读取音频文件元数据获得，精度 ±10ms），不得使用 `estimated_duration_s` 估算值替代实测时长。

#### Scenario: 时长从文件元数据读取
- **WHEN** MP3 文件生成成功并存储至 MinIO
- **THEN** 系统 SHALL 通过解析 MP3 文件头获取精确时长，写入 `duration_ms` 字段

#### Scenario: 音频文件写入失败
- **WHEN** MinIO 写入失败（如 Bucket 不存在或权限不足）
- **THEN** 系统 SHALL 返回错误 `"audio_write_failed"` 并包含失败的 `sentence_id`

---

### Requirement: TTS API 调用失败时重试
系统 SHALL 在 TTS API 返回超时（>20s）或 5xx 错误时，以指数退避策略最多重试 3 次。

#### Scenario: TTS API 临时失败后恢复
- **WHEN** TTS API 前一次返回 500，第二次成功
- **THEN** 系统 SHALL 正常返回该句音频，不中断整个批次的处理

#### Scenario: 单句三次重试全部失败
- **WHEN** 某句文案的 TTS 调用连续 3 次失败
- **THEN** 系统 SHALL 跳过该句并在输出中标记 `"status": "failed"`，继续处理剩余句子，最终汇总失败列表

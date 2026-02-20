## ADDED Requirements

### Requirement: 按三元组顺序合成最终 MP4
系统 SHALL 接受场景映射（`video-analysis` 输出）、音频片段列表（`voice-synthesis` 输出）和原始素材视频 MinIO 对象键，以 [素材片段 → 音频 → 字幕文本] 三元组为单位，调用 FFmpeg 对每个 `scene_id` 对应的视频区间进行裁剪，并与对应音频合轨，最终 concat 拼接为完整 MP4 文件，存储至 MinIO `output` Bucket。

#### Scenario: 正常合成输出 MP4
- **WHEN** 所有 `scene_id` 均有对应的场景时间戳和音频文件
- **THEN** 系统 SHALL 输出单一 MP4 文件至 MinIO `output` Bucket，对象键格式为 `{task_id}/final.mp4`，时长等于所有音频片段时长之和（音频优先策略：视频片段按音频时长裁剪）

#### Scenario: 某个 scene_id 缺少对应音频
- **WHEN** 音频列表中某个 `sentence_id` 的 `status` 为 `"failed"`
- **THEN** 系统 SHALL 跳过该场景段，在 `timeline.json` 中记录 `"skipped": true`，继续合成其余场景

---

### Requirement: 音频时长优先裁剪视频片段
系统 SHALL 以 `voice-synthesis` 返回的 `duration_ms` 为准裁剪对应的视频片段（而非使用原始 `start_ms`/`end_ms` 差值），确保每段的音视频时长完全一致。

#### Scenario: 音频比视频场景短
- **WHEN** 某场景的 `duration_ms` 小于 `end_ms - start_ms`
- **THEN** 系统 SHALL 仅截取视频场景前 `duration_ms` 毫秒的内容

#### Scenario: 音频比视频场景长
- **WHEN** 某场景的 `duration_ms` 大于 `end_ms - start_ms`
- **THEN** 系统 SHALL 循环播放该视频片段直至填满 `duration_ms`，或使用最后一帧静止画面补齐

---

### Requirement: 输出 timeline.json 记录完整时间轴
系统 SHALL 将 `timeline.json` 存储至 MinIO `output` Bucket，记录每个场景段的 `scene_id`、`sentence_id`、`start_ms`（合成视频中的起始时间）、`end_ms`（合成视频中的结束时间）、`audio_path`（MinIO 对象键）、`subtitle_text`、`skipped`（布尔值）。

#### Scenario: timeline.json 结构完整
- **WHEN** MP4 合成成功
- **THEN** `timeline.json` 中每条记录 SHALL 包含上述所有字段，且 `start_ms` 和 `end_ms` 单调递增

#### Scenario: MinIO Bucket 不存在
- **WHEN** 指定的 MinIO `output` Bucket 不存在
- **THEN** 系统 SHALL 自动创建该 Bucket，而非返回错误

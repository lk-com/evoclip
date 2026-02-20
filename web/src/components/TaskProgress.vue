<script setup lang="ts">
import { computed } from "vue";

interface AnalysisProgress {
  stage?: string;
  video_index?: number;
  total_videos?: number;
  extracted_frames?: number;
  selected_frames?: number;
  processed_frames?: number;
  total_frames?: number;
  error?: string;
}

const props = defineProps<{
  progress: number;
  status: string;
  analysisProgress?: AnalysisProgress | null;
}>();

const steps = [
  { key: "video-analysis", label: "视频分析", icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" },
  { key: "copy-generation", label: "文案生成", icon: "M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" },
  { key: "voice-synthesis", label: "语音合成", icon: "M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" },
  { key: "video-render", label: "视频渲染", icon: "M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" },
  { key: "quality-evaluation", label: "质量评估", icon: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" },
];

const normalizedStatus = computed(() => {
  if (props.status === "video-analysis-progress") {
    return "video-analysis";
  }
  return props.status;
});

const stepStatus = computed(() => {
  const idx = steps.findIndex(s => s.key === normalizedStatus.value);
  return idx === -1 ? "pending" : idx === steps.length - 1 && props.status === "quality-evaluation" ? "completed" : "processing";
});

const activeIndex = computed(() => {
  if (normalizedStatus.value === "completed") return steps.length;
  const idx = steps.findIndex(s => s.key === normalizedStatus.value);
  return idx === -1 ? 0 : idx;
});

const statusText = computed(() => {
  const map: Record<string, string> = {
    "video-analysis": "正在分析视频...",
    "copy-generation": "正在生成文案...",
    "voice-synthesis": "正在合成语音...",
    "video-render": "正在渲染视频...",
    "quality-evaluation": "正在评估质量...",
    "completed": "处理完成",
    "running": "任务处理中...",
    "queued": "等待处理",
    "failed": "处理失败",
  };
  return map[normalizedStatus.value] || normalizedStatus.value;
});

const analysisProgressText = computed(() => {
  if (normalizedStatus.value !== "video-analysis" || !props.analysisProgress) {
    return "";
  }

  const stageMap: Record<string, string> = {
    video_started: "开始分析素材",
    frames_selected: "完成抽帧",
    frame_processed: "正在分析画面",
    frame_failed: "帧分析失败（自动重试中）",
    video_completed: "素材分析完成",
    analysis_completed: "分析结果汇总完成",
  };

  const stage = props.analysisProgress.stage
    ? (stageMap[props.analysisProgress.stage] || props.analysisProgress.stage)
    : "正在分析画面";

  const videoText =
    typeof props.analysisProgress.video_index === "number" &&
    typeof props.analysisProgress.total_videos === "number"
      ? `素材 ${props.analysisProgress.video_index + 1}/${props.analysisProgress.total_videos}`
      : "";
  const frameText =
    typeof props.analysisProgress.processed_frames === "number" &&
    typeof props.analysisProgress.total_frames === "number"
      ? `帧 ${props.analysisProgress.processed_frames}/${props.analysisProgress.total_frames}`
      : typeof props.analysisProgress.selected_frames === "number" &&
          typeof props.analysisProgress.extracted_frames === "number"
        ? `抽帧 ${props.analysisProgress.selected_frames}/${props.analysisProgress.extracted_frames}`
        : "";
  const errorText =
    props.analysisProgress.stage === "frame_failed" && props.analysisProgress.error
      ? `错误: ${props.analysisProgress.error}`
      : "";

  return [stage, videoText, frameText, errorText].filter(Boolean).join(" · ");
});
</script>

<template>
  <div>
    <!-- 进度概览 -->
    <div class="flex items-start gap-4 mb-6">
      <!-- 旋转图标 -->
      <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-cta/15 border border-cta/25 shrink-0">
        <svg class="h-5 w-5 text-cta animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      </div>

      <!-- 状态文字 -->
      <div class="flex-1 min-w-0 pt-0.5">
        <div class="flex items-baseline justify-between gap-2 mb-1">
          <p class="text-sm font-semibold text-white">{{ statusText }}</p>
          <span class="text-lg font-bold text-cta tabular-nums shrink-0">{{ progress }}%</span>
        </div>
        <p v-if="analysisProgressText" class="text-xs text-slate-500 truncate">
          {{ analysisProgressText }}
        </p>
        <p v-else class="text-xs text-slate-600">AI 正在自动处理中，请耐心等待</p>
      </div>
    </div>

    <!-- 进度条 -->
    <div class="progress-track mb-6">
      <div
        class="progress-fill progress-shimmer"
        :style="{ width: `${Math.max(progress, 3)}%` }"
      ></div>
    </div>

    <!-- 步骤流 -->
    <div class="flex items-start gap-0">
      <template v-for="(step, index) in steps" :key="step.key">
        <!-- 步骤 -->
        <div class="flex-1 flex flex-col items-center gap-1.5 min-w-0">
          <!-- 节点 -->
          <div class="relative flex items-center justify-center">
            <div
              v-if="index < activeIndex"
              class="step-node-done"
            >
              <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div
              v-else-if="index === activeIndex"
              class="step-node-active"
            >
              <svg class="h-4 w-4 animate-spin-slow" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                <path stroke-linecap="round" stroke-linejoin="round" :d="step.icon" />
              </svg>
            </div>
            <div
              v-else
              class="step-node-pending"
            >
              <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                <path stroke-linecap="round" stroke-linejoin="round" :d="step.icon" />
              </svg>
            </div>
          </div>

          <!-- 标签 -->
          <span
            class="text-xs font-medium text-center leading-tight px-0.5 transition-colors"
            :class="{
              'text-white': index <= activeIndex,
              'text-slate-600': index > activeIndex,
            }"
          >{{ step.label }}</span>
        </div>

        <!-- 连接线 -->
        <div
          v-if="index < steps.length - 1"
          class="flex-shrink-0 w-6 h-px mt-4 rounded-full transition-colors duration-500"
          :class="index < activeIndex ? 'bg-cta/60' : 'bg-white/10'"
        ></div>
      </template>
    </div>
  </div>
</template>

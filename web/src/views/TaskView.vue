<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import DownloadButton from "../components/DownloadButton.vue";
import TaskProgress from "../components/TaskProgress.vue";
import VideoPreview from "../components/VideoPreview.vue";
import { getDownloadUrl } from "../api/tasks";
import { useSSE } from "../composables/useSSE";
import { useTask } from "../composables/useTask";

interface AnalysisProgressPayload {
  stage?: string;
  video_index?: number;
  total_videos?: number;
  extracted_frames?: number;
  selected_frames?: number;
  processed_frames?: number;
  total_frames?: number;
  error?: string;
}

const route = useRoute();
const router = useRouter();
const taskId = computed(() => String(route.params.id));
const { task, refresh, retry } = useTask();
const status = ref("queued");
const progress = ref(0);
const analysisProgress = ref<AnalysisProgressPayload | null>(null);

const { connect, lastEvent } = useSSE(taskId.value);

onMounted(async () => {
  await refresh(taskId.value);
  status.value = task.value?.status ?? "queued";
  progress.value = Number(task.value?.progress ?? 0);
  connect();
});

watch(lastEvent, async (event) => {
  if (!event) return;
  const eventStatus = String(event.status ?? "");
  if (eventStatus === "video-analysis-progress") {
    status.value = "video-analysis";
    analysisProgress.value = extractAnalysisProgress(event);
    return;
  }

  if (eventStatus === "heartbeat" || eventStatus.startsWith("restart_")) {
    return;
  }

  if (eventStatus) {
    status.value = eventStatus;
  }
  const eventProgress = Number(event.progress);
  if (Number.isFinite(eventProgress)) {
    progress.value = eventProgress;
  }

  if (status.value !== "video-analysis") {
    analysisProgress.value = null;
  }
  if (status.value === "completed") {
    await refresh(taskId.value);
  }
});

const videoUrl = computed(() => (task.value?.output_video_key ? getDownloadUrl(taskId.value) : ""));
const isCompleted = computed(() => status.value === "completed");
const isFailed = computed(() => status.value === "failed");

const goHome = () => {
  router.push("/");
};

const handleRetry = async () => {
  await retry(taskId.value);
  status.value = "queued";
  progress.value = 0;
  analysisProgress.value = null;
  connect();
};

const toOptionalNumber = (value: unknown): number | undefined => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
};

const extractAnalysisProgress = (event: Record<string, unknown>): AnalysisProgressPayload => ({
  stage: typeof event.stage === "string" ? event.stage : undefined,
  video_index: toOptionalNumber(event.video_index),
  total_videos: toOptionalNumber(event.total_videos),
  extracted_frames: toOptionalNumber(event.extracted_frames),
  selected_frames: toOptionalNumber(event.selected_frames),
  processed_frames: toOptionalNumber(event.processed_frames),
  total_frames: toOptionalNumber(event.total_frames),
  error: typeof event.error === "string" ? event.error : undefined,
});
</script>

<template>
  <div class="min-h-screen py-10">
    <div class="max-w-2xl mx-auto px-6">

      <!-- 页头导航 -->
      <div class="flex items-center justify-between mb-8 animate-fade-in">
        <button
          class="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors group"
          @click="goHome"
        >
          <svg class="h-4 w-4 transition-transform group-hover:-translate-x-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          返回首页
        </button>

        <!-- 任务 ID -->
        <div class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/4 border border-white/8">
          <span class="text-xs text-slate-500">Task</span>
          <code class="text-xs font-mono text-slate-300">{{ taskId.slice(0, 8) }}...</code>
        </div>
      </div>

      <!-- 主卡片 -->
      <div class="glass-card animate-slide-up animate-delay-100">
        <!-- 卡片头部 -->
        <div class="px-6 py-5 border-b border-white/6 flex items-center gap-4">
          <div class="icon-box-md icon-box-gradient">
            <svg class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <h1 class="text-base font-semibold text-white">视频生成任务</h1>
            <p class="text-xs text-slate-500 mt-0.5">AI 正在自动处理您的视频内容</p>
          </div>
          <!-- 状态徽章 -->
          <div v-if="isCompleted" class="badge-success">
            <svg class="h-3 w-3" fill="currentColor" viewBox="0 0 8 8">
              <circle cx="4" cy="4" r="3"/>
            </svg>
            已完成
          </div>
          <div v-else-if="isFailed" class="badge-error">
            <svg class="h-3 w-3" fill="currentColor" viewBox="0 0 8 8">
              <circle cx="4" cy="4" r="3"/>
            </svg>
            失败
          </div>
          <div v-else class="badge-processing">
            <span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
            处理中
          </div>
        </div>

        <!-- 卡片内容 -->
        <div class="p-6">
          <!-- 进度视图 -->
          <TaskProgress
            v-if="!isCompleted && !isFailed"
            :progress="progress"
            :status="status"
            :analysis-progress="analysisProgress"
          />

          <!-- 完成状态 -->
          <div v-else-if="isCompleted" class="space-y-5">
            <!-- 成功提示 -->
            <div class="flex items-center gap-4 p-4 rounded-xl bg-emerald-500/8 border border-emerald-500/20">
              <div class="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/15 shrink-0">
                <svg class="h-5 w-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <div>
                <p class="text-sm font-semibold text-white">视频生成成功</p>
                <p class="text-xs text-slate-400 mt-0.5">您的营销视频已准备好下载</p>
              </div>
            </div>

            <!-- 视频预览 -->
            <VideoPreview v-if="videoUrl" :src="videoUrl" />

            <!-- 下载按钮 -->
            <div v-if="videoUrl" class="flex justify-center pt-1">
              <DownloadButton :href="videoUrl" :filename="`evoclip-${taskId}.mp4`" />
            </div>
          </div>

          <!-- 失败状态 -->
          <div v-else-if="isFailed" class="space-y-5">
            <div class="flex items-center gap-4 p-4 rounded-xl bg-rose-500/8 border border-rose-500/20">
              <div class="flex h-10 w-10 items-center justify-center rounded-full bg-rose-500/15 shrink-0">
                <svg class="h-5 w-5 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <div>
                <p class="text-sm font-semibold text-white">任务处理失败</p>
                <p class="text-xs text-slate-400 mt-0.5">请检查素材文件后重新尝试</p>
              </div>
            </div>
            <div class="flex gap-3">
              <button class="btn-primary flex-1 text-sm" @click="handleRetry">
                <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                重新尝试
              </button>
              <button class="btn-secondary flex-1 text-sm" @click="goHome">
                返回首页
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 使用建议卡片（完成后展示） -->
      <div v-if="isCompleted" class="mt-5 glass-card p-5 animate-slide-up animate-delay-200">
        <h3 class="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <svg class="h-4 w-4 text-cta" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          使用建议
        </h3>
        <ul class="space-y-2.5">
          <li class="flex items-start gap-2.5 text-xs text-slate-400">
            <svg class="h-3.5 w-3.5 text-emerald-400 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>下载视频后可在本地进行进一步编辑</span>
          </li>
          <li class="flex items-start gap-2.5 text-xs text-slate-400">
            <svg class="h-3.5 w-3.5 text-emerald-400 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>可以在社交媒体平台分享您的营销视频</span>
          </li>
        </ul>
      </div>

    </div>
  </div>
</template>

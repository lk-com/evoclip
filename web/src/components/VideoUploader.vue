<script setup lang="ts">
import { ref } from "vue";

const emit = defineEmits<{ upload: [File[]] }>();
const files = ref<File[]>([]);
const dragging = ref(false);
const error = ref<string | null>(null);

const accepted = ["video/mp4", "video/quicktime"];
const maxBytes = 500 * 1024 * 1024;
const maxFiles = 10;

const validate = (candidate: File): boolean => {
  if (!accepted.includes(candidate.type)) {
    error.value = "仅支持 MP4/MOV 文件";
    return false;
  }
  if (candidate.size > maxBytes) {
    error.value = "单个文件大小不能超过 500MB";
    return false;
  }
  return true;
};

const pick = (candidates: File[]) => {
  if (!candidates.length) return;
  if (candidates.length > maxFiles) {
    error.value = `最多上传 ${maxFiles} 个素材`;
    return;
  }
  const valid = candidates.filter(validate);
  if (!valid.length) return;
  files.value = valid;
  error.value = null;
};

const onChange = (event: Event) => {
  const input = event.target as HTMLInputElement;
  pick(Array.from(input.files ?? []));
};

const onDrop = (event: DragEvent) => {
  event.preventDefault();
  dragging.value = false;
  pick(Array.from(event.dataTransfer?.files ?? []));
};

const onDragOver = (event: DragEvent) => {
  event.preventDefault();
  dragging.value = true;
};

const onDragLeave = (event: DragEvent) => {
  event.preventDefault();
  dragging.value = false;
};

const submit = () => {
  if (files.value.length) emit("upload", files.value);
};

const formatSize = (bytes: number) => {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
};

const clearFile = (index: number) => {
  files.value = files.value.filter((_, idx) => idx !== index);
  if (!files.value.length) error.value = null;
};

const clearAll = () => {
  files.value = [];
  error.value = null;
};
</script>

<template>
  <div>
    <!-- 头部 -->
    <div class="flex items-center justify-between mb-3">
      <div>
        <p class="text-sm font-medium text-slate-200 flex items-center gap-1.5">
          <svg class="h-3.5 w-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          素材视频
          <span class="text-cta">*</span>
        </p>
        <p class="text-xs text-slate-500 mt-0.5">支持 1-10 个 MP4/MOV 文件，单文件最大 500MB</p>
      </div>
      <button
        v-if="files.length"
        class="text-xs text-slate-500 hover:text-rose-400 transition-colors"
        @click="clearAll"
      >
        清空全部
      </button>
    </div>

    <!-- 上传区 -->
    <div
      class="upload-zone"
      :class="dragging ? 'upload-zone-active' : 'border-white/15'"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <!-- 拖拽图标 -->
      <div class="mb-3 flex justify-center">
        <div
          class="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/5 border border-white/10 transition-all"
          :class="dragging && 'border-cta/50 bg-cta/8'"
        >
          <svg
            class="h-6 w-6 transition-colors"
            :class="dragging ? 'text-cta' : 'text-slate-500'"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
        </div>
      </div>

      <p class="text-sm text-slate-300 mb-1">
        {{ dragging ? '松开鼠标上传文件' : '拖拽素材视频到这里，或点击选择' }}
      </p>
      <p class="text-xs text-slate-600">支持多选上传 · MP4 / MOV</p>

      <input
        class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
        type="file"
        accept="video/mp4,video/quicktime"
        multiple
        @change="onChange"
      />
    </div>

    <!-- 文件列表 -->
    <div v-if="files.length" class="mt-3 space-y-2">
      <div
        v-for="(file, index) in files"
        :key="file.name + index"
        class="file-item"
      >
        <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-500/15 border border-rose-500/20 shrink-0">
          <svg class="h-4 w-4 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium text-white truncate">{{ file.name }}</p>
          <p class="text-xs text-slate-500">{{ formatSize(file.size) }}</p>
        </div>
        <button
          class="p-1.5 rounded-lg text-slate-600 hover:text-rose-400 hover:bg-rose-500/10 transition-all"
          @click="clearFile(index)"
          aria-label="移除文件"
        >
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="mt-3 flex items-center gap-2 text-xs text-rose-400">
      <svg class="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ error }}
    </div>

    <!-- 提交按钮 -->
    <button
      class="btn-primary w-full mt-5 text-sm"
      :disabled="!files.length"
      @click="submit"
    >
      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
      </svg>
      {{ files.length ? `开始生成视频（已选 ${files.length} 个）` : '请先选择素材视频' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";

const emit = defineEmits<{ change: [File[]] }>();
const files = ref<File[]>([]);
const dragging = ref(false);
const error = ref<string | null>(null);

const accepted = ["video/mp4", "video/quicktime"];
const maxBytes = 500 * 1024 * 1024;

const validate = (candidate: File): boolean => {
  if (!accepted.includes(candidate.type)) {
    error.value = "仅支持 MP4/MOV 文件";
    return false;
  }
  if (candidate.size > maxBytes) {
    error.value = "文件大小不能超过 500MB";
    return false;
  }
  return true;
};

const pick = (candidates: File[]) => {
  if (!candidates.length) return;
  const valid = candidates.filter(validate);
  if (!valid.length) return;
  error.value = null;
  files.value = valid;
};

const onChange = (event: Event) => {
  const input = event.target as HTMLInputElement;
  const selected = Array.from(input.files ?? []);
  pick(selected);
};

const onDrop = (event: DragEvent) => {
  event.preventDefault();
  dragging.value = false;
  const selected = Array.from(event.dataTransfer?.files ?? []);
  pick(selected);
};

const onDragOver = (event: DragEvent) => {
  event.preventDefault();
  dragging.value = true;
};

const onDragLeave = (event: DragEvent) => {
  event.preventDefault();
  dragging.value = false;
};

const clearFile = (index: number) => {
  files.value = files.value.filter((_, idx) => idx !== index);
  if (!files.value.length) {
    error.value = null;
  }
};

const clearAll = () => {
  files.value = [];
  error.value = null;
};

const formatSize = (bytes: number) => {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
};

watch(files, (value) => {
  emit("change", value);
});
</script>

<template>
  <div>
    <!-- 头部 -->
    <div class="flex items-center justify-between mb-3">
      <div>
        <p class="text-sm font-medium text-slate-300 flex items-center gap-1.5">
          <svg class="h-3.5 w-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
          配音参考视频
          <span class="text-xs font-normal text-slate-500 ml-1">（可选）</span>
        </p>
        <p class="text-xs text-slate-500 mt-0.5">上传参考视频，系统将提取音色进行配音克隆</p>
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
      :class="dragging ? 'upload-zone-active' : 'border-white/12'"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <div class="mb-2.5 flex justify-center">
        <div
          class="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/5 border border-white/10 transition-all"
          :class="dragging && 'border-violet-500/40 bg-violet-500/8'"
        >
          <svg
            class="h-5 w-5 transition-colors"
            :class="dragging ? 'text-violet-400' : 'text-slate-500'"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
        </div>
      </div>

      <p class="text-sm text-slate-400 mb-1">
        {{ dragging ? '松开鼠标上传文件' : '拖拽参考视频到这里，或点击选择' }}
      </p>
      <p class="text-xs text-slate-600">MP4 / MOV · 最大 500MB</p>

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
        <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/15 border border-violet-500/20 shrink-0">
          <svg class="h-4 w-4 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
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
  </div>
</template>

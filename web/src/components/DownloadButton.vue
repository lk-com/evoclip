<script setup lang="ts">
defineProps<{ href: string; filename?: string }>();
</script>

<template>
  <a
    class="btn-primary gap-2.5 px-8 py-3.5 text-sm"
    :href="href"
    :download="filename ?? 'evoclip-output.mp4'"
  >
    <svg class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
      <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
    </svg>
    下载视频
  </a>
</template>

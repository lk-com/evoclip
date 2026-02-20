<script setup lang="ts">
defineProps<{ src: string }>();
</script>

<template>
  <div class="overflow-hidden rounded-2xl border border-white/8" style="background:#000;box-shadow:0 8px 32px rgba(0,0,0,0.6)">
    <div class="relative">
      <video
        class="w-full aspect-video block"
        controls
        :src="src"
        preload="metadata"
      >
        您的浏览器不支持视频播放
      </video>
    </div>
  </div>
</template>

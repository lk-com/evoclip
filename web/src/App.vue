<script setup lang="ts">
import { RouterView } from "vue-router";
</script>

<template>
  <div class="min-h-screen">
    <!-- 噪点纹理 -->
    <div class="noise-overlay" aria-hidden="true"></div>

    <!-- 背景光晕 -->
    <div class="fixed inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
      <div class="absolute -top-32 left-[15%] w-[600px] h-[600px] rounded-full opacity-20 animate-glow-pulse"
           style="background: radial-gradient(circle, rgba(124,58,237,0.6) 0%, transparent 70%); filter: blur(80px);"></div>
      <div class="absolute top-[30%] right-[5%] w-[400px] h-[400px] rounded-full opacity-15 animate-glow-pulse animate-delay-400"
           style="background: radial-gradient(circle, rgba(225,29,72,0.5) 0%, transparent 70%); filter: blur(60px);"></div>
      <div class="absolute bottom-0 left-[40%] w-[500px] h-[300px] rounded-full opacity-10"
           style="background: radial-gradient(circle, rgba(225,29,72,0.4) 0%, transparent 70%); filter: blur(80px);"></div>
    </div>

    <!-- 导航栏 -->
    <nav class="nav-bar">
      <div class="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <!-- Logo -->
        <router-link to="/" class="flex items-center gap-3 group" aria-label="EvoClip 首页">
          <div class="icon-box-md icon-box-gradient transition-all duration-300 group-hover:scale-105 group-hover:shadow-glow">
            <svg class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </div>
          <div class="flex flex-col">
            <span class="text-base font-bold text-white leading-none tracking-wide">EvoClip</span>
            <span class="text-xs text-slate-500 leading-none mt-0.5">AI 视频生成</span>
          </div>
        </router-link>

        <!-- 右侧操作区 -->
        <div class="flex items-center gap-3">
          <div class="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/5 border border-white/8">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            <span class="text-xs text-slate-400">系统在线</span>
          </div>
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            class="flex items-center gap-2 px-3 py-2 rounded-xl bg-white/5 border border-white/8
                   text-slate-400 hover:text-white hover:bg-white/10 hover:border-white/15 transition-all duration-200"
            aria-label="GitHub"
          >
            <svg class="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
            </svg>
            <span class="hidden sm:inline text-xs font-medium">GitHub</span>
          </a>
        </div>
      </div>
    </nav>

    <!-- 主内容 -->
    <main class="relative z-10">
      <RouterView />
    </main>
  </div>
</template>

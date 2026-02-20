<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import VideoUploader from "../components/VideoUploader.vue";
import VoiceSampleUploader from "../components/VoiceSampleUploader.vue";
import { useTask } from "../composables/useTask";

const router = useRouter();
const productDescription = ref("");
const voiceSamples = ref<File[]>([]);
const error = ref<string | null>(null);
const { create, loading } = useTask();

const upload = async (files: File[]) => {
  error.value = null;
  if (!productDescription.value.trim()) {
    error.value = "请输入商品描述";
    return;
  }
  if (!files.length) {
    error.value = "请至少上传一个素材视频";
    return;
  }

  const created = await create(
    files,
    productDescription.value,
    voiceSamples.value.length ? voiceSamples.value : undefined
  );
  await router.push(`/task/${created.task_id}`);
};

const updateVoiceSamples = (files: File[]) => {
  voiceSamples.value = files;
};

const features = [
  {
    icon: "M13 10V3L4 14h7v7l9-11h-7z",
    title: "AI 智能分析",
    description: "自动识别商品特点和卖点",
    color: "from-violet-500/20 to-violet-600/10",
    iconColor: "text-violet-400",
    borderColor: "border-violet-500/20",
  },
  {
    icon: "M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z",
    title: "自动文案生成",
    description: "生成吸引眼球的推广文案",
    color: "from-rose-500/20 to-rose-600/10",
    iconColor: "text-rose-400",
    borderColor: "border-rose-500/20",
  },
  {
    icon: "M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z",
    title: "语音合成",
    description: "专业配音，提升视频质量",
    color: "from-sky-500/20 to-sky-600/10",
    iconColor: "text-sky-400",
    borderColor: "border-sky-500/20",
  },
  {
    icon: "M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z",
    title: "视频渲染",
    description: "快速生成高质量视频",
    color: "from-emerald-500/20 to-emerald-600/10",
    iconColor: "text-emerald-400",
    borderColor: "border-emerald-500/20",
  }
];
</script>

<template>
  <div class="min-h-screen">
    <!-- Hero 区域 -->
    <section class="relative pt-16 pb-12 md:pt-24 md:pb-16 overflow-hidden">
      <div class="max-w-4xl mx-auto px-6 text-center">
        <!-- 标签 -->
        <div class="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 border border-white/10
                    text-xs text-slate-400 mb-8 animate-fade-in">
          <span class="w-1.5 h-1.5 rounded-full bg-cta animate-pulse shrink-0"></span>
          自进化 AI 视频生成引擎 · Agent + MCP + Skill 架构
        </div>

        <!-- 主标题 -->
        <h1 class="text-5xl md:text-7xl font-extrabold mb-5 leading-[1.1] tracking-tight animate-slide-up animate-delay-100">
          <span class="text-gradient">一键生成</span>
          <br />
          <span class="text-white">营销视频</span>
        </h1>

        <p class="text-base md:text-lg text-slate-400 mb-10 max-w-xl mx-auto leading-relaxed animate-slide-up animate-delay-200 text-balance">
          上传素材视频，AI 自动完成视频分析、文案创作、语音配音、视频剪辑，
          <span class="text-slate-300">音画同步误差 &lt;200ms</span>
        </p>

        <!-- 统计数据 -->
        <div class="flex flex-wrap items-center justify-center gap-8 animate-slide-up animate-delay-300">
          <div class="text-center">
            <div class="text-2xl font-bold text-white">5</div>
            <div class="text-xs text-slate-500 mt-0.5">处理阶段</div>
          </div>
          <div class="w-px h-8 bg-white/10"></div>
          <div class="text-center">
            <div class="text-2xl font-bold text-white">&lt;200ms</div>
            <div class="text-xs text-slate-500 mt-0.5">音画同步误差</div>
          </div>
          <div class="w-px h-8 bg-white/10"></div>
          <div class="text-center">
            <div class="text-2xl font-bold text-white">10个</div>
            <div class="text-xs text-slate-500 mt-0.5">最大素材数</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 主表单区域 -->
    <section class="relative pb-20">
      <div class="max-w-2xl mx-auto px-6">
        <!-- 区域标题 -->
        <div class="flex items-center gap-3 mb-5 animate-fade-in animate-delay-300">
          <div class="flex-1 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent"></div>
          <div class="flex items-center gap-2 text-sm text-slate-400">
            <svg class="h-4 w-4 text-cta" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
            开始创建任务
          </div>
          <div class="flex-1 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent"></div>
        </div>

        <!-- 主卡片 -->
        <div class="glass-card p-6 md:p-8 animate-slide-up animate-delay-400">
          <!-- 商品描述 -->
          <div class="mb-5">
            <label class="flex items-center gap-2 text-sm font-medium text-slate-300 mb-2.5">
              <svg class="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              商品描述
              <span class="text-cta">*</span>
            </label>
            <textarea
              v-model="productDescription"
              class="input-field min-h-28 resize-none text-sm leading-relaxed"
              placeholder="请描述您的商品特点、目标用户、核心卖点等，AI 将据此生成最合适的文案..."
            ></textarea>
          </div>

          <!-- 分隔线 -->
          <div class="divider my-5"></div>

          <!-- 语音样本上传 -->
          <VoiceSampleUploader class="mb-5" @change="updateVoiceSamples" />

          <!-- 视频上传 -->
          <VideoUploader @upload="upload" />

          <!-- 加载状态 -->
          <div v-if="loading" class="mt-5 flex items-center justify-center gap-3 py-3 px-4
                                     rounded-xl bg-white/3 border border-white/8">
            <svg class="h-4 w-4 animate-spin text-cta shrink-0" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span class="text-sm text-slate-400">正在创建任务，请稍候...</span>
          </div>

          <!-- 错误提示 -->
          <div v-if="error" class="mt-4 flex items-center gap-2.5 py-3 px-4
                                   rounded-xl bg-rose-500/8 border border-rose-500/20">
            <svg class="h-4 w-4 text-rose-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p class="text-sm text-rose-400">{{ error }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- 功能特性 -->
    <section class="py-16">
      <div class="max-w-5xl mx-auto px-6">
        <div class="text-center mb-10">
          <h2 class="text-xl font-semibold text-white mb-2">全自动 AI 工作流</h2>
          <p class="text-sm text-slate-500">从素材到成品，四大阶段自动完成</p>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div
            v-for="(feature, index) in features"
            :key="feature.title"
            class="glass-card-hover p-5 cursor-default animate-slide-up"
            :class="`animate-delay-${(index + 1) * 100}`"
          >
            <!-- 序号 -->
            <div class="text-xs font-mono text-slate-600 mb-3">0{{ index + 1 }}</div>
            <!-- 图标 -->
            <div
              class="icon-box-md mb-4 bg-gradient-to-br border"
              :class="[feature.color, feature.borderColor]"
            >
              <svg class="h-5 w-5" :class="feature.iconColor" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                <path stroke-linecap="round" stroke-linejoin="round" :d="feature.icon" />
              </svg>
            </div>
            <h3 class="font-semibold text-white text-sm mb-1.5">{{ feature.title }}</h3>
            <p class="text-xs text-slate-500 leading-relaxed">{{ feature.description }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- 页脚 -->
    <footer class="py-8 border-t border-white/5">
      <div class="max-w-5xl mx-auto px-6 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <div class="icon-box-sm icon-box-gradient">
            <svg class="h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </div>
          <span class="text-xs text-slate-500">EvoClip · AI 视频生成平台</span>
        </div>
        <p class="text-xs text-slate-600">Agent + MCP + Skill 自进化架构</p>
      </div>
    </footer>
  </div>
</template>

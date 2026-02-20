import { ref } from "vue";

import { createTask, getTask, retryTask } from "../api/tasks";

export function useTask() {
  const task = ref<any>(null);
  const loading = ref(false);

  const create = async (files: File[], productDescription: string, voiceSamples?: File[]) => {
    loading.value = true;
    try {
      const created = await createTask({ files, productDescription, voiceSamples });
      task.value = await getTask(created.task_id);
      return created;
    } finally {
      loading.value = false;
    }
  };

  const refresh = async (taskId: string) => {
    loading.value = true;
    try {
      task.value = await getTask(taskId);
      return task.value;
    } finally {
      loading.value = false;
    }
  };

  const retry = async (taskId: string) => {
    loading.value = true;
    try {
      const result = await retryTask(taskId);
      task.value = await getTask(result.task_id);
      return result;
    } finally {
      loading.value = false;
    }
  };

  return {
    task,
    loading,
    create,
    refresh,
    retry
  };
}

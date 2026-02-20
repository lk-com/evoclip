import client from "./client";

export interface CreateTaskPayload {
  files: File[];
  productDescription: string;
  voiceSamples?: File[];
}

export async function createTask(payload: CreateTaskPayload): Promise<{ task_id: string }> {
  const form = new FormData();
  payload.files.forEach((file) => {
    form.append("videos", file);
  });
  form.append("product_description", payload.productDescription);
  payload.voiceSamples?.forEach((sample) => {
    form.append("voice_samples", sample);
  });
  const { data } = await client.post("/tasks", form, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data;
}

export async function getTask(taskId: string): Promise<any> {
  const { data } = await client.get(`/tasks/${taskId}`);
  return data;
}

export function getDownloadUrl(taskId: string): string {
  return `/api/tasks/${taskId}/download`;
}

export async function retryTask(taskId: string): Promise<{ task_id: string }> {
  const { data } = await client.post(`/tasks/${taskId}/retry`);
  return data;
}

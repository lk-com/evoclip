import { onBeforeUnmount, ref } from "vue";

export function useSSE(taskId: string) {
  const connected = ref(false);
  const lastEvent = ref<Record<string, unknown> | null>(null);
  const error = ref<string | null>(null);
  let source: EventSource | null = null;

  const connect = () => {
    source = new EventSource(`/api/tasks/${taskId}/events`);
    source.onopen = () => {
      connected.value = true;
      error.value = null;
    };
    source.onmessage = (event) => {
      try {
        lastEvent.value = JSON.parse(event.data);
      } catch {
        lastEvent.value = { raw: event.data };
      }
    };
    source.onerror = () => {
      connected.value = false;
      error.value = "sse_disconnected";
      source?.close();
      setTimeout(connect, 1_000);
    };
  };

  const disconnect = () => {
    connected.value = false;
    source?.close();
  };

  onBeforeUnmount(disconnect);

  return {
    connect,
    disconnect,
    connected,
    lastEvent,
    error
  };
}

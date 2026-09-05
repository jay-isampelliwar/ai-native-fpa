/**
 * Reading the planner's server-sent events, so the chat shows progress instead of a spinner.
 *
 * `EventSource` cannot be used here because the endpoint is a POST carrying the message body, so the
 * stream is read from `fetch` directly. That means parsing the SSE framing by hand, which is why this
 * lives in one place rather than inside a component.
 *
 * Events are separated by a blank line and may arrive split across chunks, so the buffer keeps
 * whatever does not yet end in a delimiter. Parsing per chunk instead would silently drop the tail of
 * any event unlucky enough to straddle a boundary - rare locally, common over a real network.
 *
 * The terminal `done` event carries exactly what the non-streaming endpoint returns. A caller may
 * ignore every progress event and still be correct, which is what keeps the streaming path from
 * becoming a second, subtly different source of truth about what the answer was.
 */

import type { MessageResponse, ProgressEvent } from "@/lib/types";

interface StreamHandlers {
  onProgress?: (event: ProgressEvent) => void;
  onDone: (response: MessageResponse) => void;
  onError: (message: string) => void;
}

export async function streamMessage(
  userId: number,
  message: string,
  conversationId: string | undefined,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/v1/planner/messages/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      message,
      conversation_id: conversationId ?? null,
    }),
    signal,
  });

  if (!response.ok || !response.body) {
    handlers.onError("The planner could not be reached.");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();

    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    const chunks = buffer.split("\n\n");

    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      dispatch(chunk, handlers);
    }
  }

  if (buffer.trim()) {
    dispatch(buffer, handlers);
  }
}

function dispatch(chunk: string, handlers: StreamHandlers): void {
  const lines = chunk.split("\n");

  const nameLine = lines.find((line) => line.startsWith("event:"));
  const dataLine = lines.find((line) => line.startsWith("data:"));

  if (!nameLine || !dataLine) return;

  const name = nameLine.slice("event:".length).trim();
  const payload = dataLine.slice("data:".length).trim();

  try {
    const parsed: unknown = JSON.parse(payload);

    if (name === "progress") {
      handlers.onProgress?.(parsed as ProgressEvent);
    } else if (name === "done") {
      handlers.onDone(parsed as MessageResponse);
    } else if (name === "error") {
      handlers.onError("The request could not be completed.");
    }
  } catch {
    handlers.onError("The planner sent a response that could not be read.");
  }
}

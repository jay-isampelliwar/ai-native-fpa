/**
 * Sending one message as a run, then reading that run's server-sent events.
 *
 * A turn is two calls. `POST /api/runs` saves the message and starts the agent in the background,
 * answering at once with a `run_id`. `GET /api/runs/{run_id}/events` then streams the reply. The
 * `client_request_id` is made here, once per message, and sent again on a retry, so a POST whose
 * answer was lost on the network returns the same run instead of starting a second one.
 *
 * Events are separated by a blank line and may arrive split across chunks, so the buffer keeps
 * whatever does not yet end in a delimiter.
 *
 * `assistant.snapshot` is the reply so far for a listener that joined late and replaces the text.
 * `assistant.delta` is the next piece and is appended. A run ends with exactly one of
 * `run.completed`, `run.failed` or `run.cancelled`.
 *
 * `tool.started` and `tool.finished` mark each tool the planner calls, keyed by the call's id. A
 * late listener gets the latest step of every tool so far before the snapshot.
 *
 * `approval.required` means the run paused on a risky tool, such as a delete, and the stream ends
 * there. The run carries on only after `runs.decide`, and its events are then read again with
 * `followRun`. Opening a paused chat sends the same event at once, so the card comes back.
 */

import { reportUnauthorized } from "@/lib/api";
import type { ApprovalRequest, RunResponse, ToolStep } from "@/lib/types";

export interface StreamHandlers {
  /** The run was accepted; keep its conversation id to continue the same chat. */
  onRun?: (run: RunResponse) => void;
  /** The whole reply so far, sent first to a listener that joined late. Replaces the text. */
  onSnapshot?: (text: string) => void;
  /** A piece of the answer as the model writes it. Appended to the text. */
  onToken?: (text: string) => void;
  /** A tool started or finished. The same id arrives again when its status changes. */
  onTool?: (step: ToolStep) => void;
  /** The run paused for the person to approve or reject one tool. The stream ends after this. */
  onApproval?: (request: ApprovalRequest) => void;
  onDone: (text: string) => void;
  /** The run was stopped on request. Carries the reply written before it stopped. */
  onCancelled?: (text: string) => void;
  onError: (message: string) => void;
}

const POST_ATTEMPTS = 2;

async function createRun(
  conversationId: number | null,
  message: string,
  signal?: AbortSignal,
): Promise<Response> {
  const body = JSON.stringify({
    conversation_id: conversationId,
    client_request_id: crypto.randomUUID(),
    message,
  });

  for (let attempt = 1; ; attempt++) {
    try {
      return await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        signal,
      });
    } catch (error) {
      if (attempt >= POST_ATTEMPTS || signal?.aborted) throw error;
    }
  }
}

function describeFailure(status: number): string {
  if (status === 401) {
    reportUnauthorized();
    return "Your session has ended. Please sign in again.";
  }
  if (status === 409) return "A reply is still being written in this chat. Please wait for it to finish.";
  if (status === 404) return "This conversation could not be found. Start a new chat.";
  return "The planner could not be reached.";
}

/** Ask the backend to stop a run. The stream then ends with `run.cancelled`. */
export async function cancelRun(runId: number): Promise<void> {
  await fetch(`/api/runs/${runId}/cancel`, { method: "POST" });
}

export async function streamMessage(
  conversationId: number | null,
  message: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const created = await createRun(conversationId, message, signal);

  if (!created.ok) {
    handlers.onError(describeFailure(created.status));
    return;
  }

  const run = (await created.json()) as RunResponse;

  handlers.onRun?.(run);

  await followRun(run.run_id, handlers, signal);
}

/**
 * Read one run's events until it ends.
 *
 * Also used on its own when a past chat is opened while its reply is still being written: the
 * first event is then a snapshot of the text so far, and the deltas carry on from there.
 */
export async function followRun(
  runId: number,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/runs/${runId}/events`, { signal });

  if (!response.ok || !response.body) {
    handlers.onError(response.ok ? "The planner could not be reached." : describeFailure(response.status));
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

/** The step status for a `tool.finished` event, which says ok, error or rejected. */
function finishedStatus(status: string | undefined): ToolStep["status"] {
  if (status === "error") return "error";
  if (status === "rejected") return "rejected";

  return "ok";
}

function dispatch(chunk: string, handlers: StreamHandlers): void {
  const lines = chunk.split("\n");

  const nameLine = lines.find((line) => line.startsWith("event:"));
  const dataLine = lines.find((line) => line.startsWith("data:"));

  if (!nameLine || !dataLine) return;

  const name = nameLine.slice("event:".length).trim();
  const payload = dataLine.slice("data:".length).trim();

  try {
    const parsed = JSON.parse(payload) as {
      text?: string;
      message?: string;
      id?: string;
      name?: string;
      label?: string;
      status?: string;
    };

    if (name === "assistant.snapshot") {
      handlers.onSnapshot?.(parsed.text ?? "");
    } else if (name === "assistant.delta") {
      handlers.onToken?.(parsed.text ?? "");
    } else if (name === "tool.started" || name === "tool.finished") {
      handlers.onTool?.({
        id: parsed.id ?? "",
        name: parsed.name ?? "",
        label: parsed.label || parsed.name || "Using a tool",
        status: name === "tool.started" ? "running" : finishedStatus(parsed.status),
      });
    } else if (name === "approval.required") {
      handlers.onApproval?.(parsed as unknown as ApprovalRequest);
    } else if (name === "run.completed") {
      handlers.onDone(parsed.text ?? "");
    } else if (name === "run.failed") {
      handlers.onError(parsed.message ?? "The request could not be completed.");
    } else if (name === "run.cancelled") {
      handlers.onCancelled?.(parsed.text ?? "");
    }
  } catch {
    handlers.onError("The planner sent a response that could not be read.");
  }
}

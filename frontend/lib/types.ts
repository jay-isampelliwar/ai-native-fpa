/**
 * The shapes the backend actually returns, mirrored by hand rather than generated.
 *
 * There are two of them, because the backend has two endpoints: registering an id, and one streaming
 * chat turn. Everything else this file held - typed blocks, the workspace panel, imports and their
 * staged rows, alerts, goals, holdings, conversations, approvals - described routes that have been
 * removed, and a type for a field the backend cannot send is how a client ends up rendering an empty
 * section forever.
 *
 * `MessageResponse` is what the stream's closing `done` event carries. The thread id comes back on
 * every turn because the first one invents it, and sending it again is what continues the same
 * conversation.
 *
 * `ProgressEvent` is one line of "what is happening" while the answer is being written. It carries no
 * skill name any more; there is one node in the graph, so there is nothing to name.
 */

export interface MessageResponse {
  conversation_id: string;
  response: string;
}

export interface ProgressEvent {
  node: string;
  label: string;
}

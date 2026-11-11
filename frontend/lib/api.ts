/**
 * One typed client for the backend, so no component builds a URL or handles an error shape itself.
 *
 * Every call goes through `request`, which means one place decides what a failure looks like. A
 * component that has to interpret a 404 differently from a 500 will eventually get it wrong, and a
 * financial interface that renders a failed fetch as an empty portfolio is worse than one that says
 * it could not load.
 *
 * `ApiError` carries the status and the backend's `detail`. The backend deliberately returns 404 for
 * a record the caller does not own rather than 403, so a not-found here genuinely means "not yours or
 * not there" and should be phrased that way to a reader.
 *
 * Who is calling is decided by the httpOnly session cookie the backend sets at sign-in. The browser
 * sends it with every same-origin request, so nothing here attaches a token. A 401 from any route
 * other than the auth ones means the session ended; `reportUnauthorized` tells the session store,
 * and the shell then sends the page to sign-in.
 *
 * The chat's turns do not appear here because a turn is a run whose reply is read
 * as server-sent events rather than JSON, so `lib/stream.ts` handles both of its calls. Uploads
 * and their review go through `documents`.
 *
 * Nothing here caches. Financial figures shown to a user must be the ones the backend just computed,
 * and a stale surplus rendered as current is exactly the failure the whole backend design avoids.
 */

import type {
  ApprovalDecision,
  ApprovalEdits,
  ApprovalOutcome,
  RunResponse,
  ConversationDetail,
  CurrentUser,
  ConversationList,
  ConversationSummary,
  DocumentView,
  ImportFields,
  InstrumentChoice,
  QuestionAnswer,
  RowEdit,
  SheetChoice,
} from "@/lib/types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

let unauthorizedHandler: (() => void) | null = null;

/** Register what happens when the backend says the session is gone. The session store does this. */
export function onUnauthorized(handler: () => void): void {
  unauthorizedHandler = handler;
}

/** Tell the session store that the backend answered 401. */
export function reportUnauthorized(): void {
  unauthorizedHandler?.();
}

/**
 * The backend's reason as one line. Most routes send text; the import routes send every reason as
 * a list, and validation errors come as objects with a `msg`.
 */
function readDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "string" ? item : (item as { msg?: string })?.msg ?? ""))
      .filter(Boolean)
      .join("; ");
  }

  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    cache: "no-store",
    headers: {
      ...(init?.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });

  if (response.status === 401 && !path.startsWith("/api/auth/")) {
    reportUnauthorized();
  }

  if (!response.ok) {
    let detail = response.statusText;

    try {
      const body = (await response.json()) as { detail?: unknown };
      detail = readDetail(body.detail) ?? detail;
    } catch {
      // A non-JSON error body is still an error; the status alone is enough to report.
    }

    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const conversations = {
  /** The person's chats for the history list, most recently active first. */
  list(limit = 50) {
    return request<ConversationList>(`/api/conversations?limit=${limit}`);
  },

  /** One chat with its messages, and the run still writing a reply, if any. */
  get(conversationId: number) {
    return request<ConversationDetail>(`/api/conversations/${conversationId}`);
  },

  /** Give one chat a new title; its place in the history list stays the same. */
  rename(conversationId: number, title: string) {
    return request<ConversationSummary>(`/api/conversations/${conversationId}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
  },

  /** Soft delete one chat; the backend keeps its rows but hides it everywhere. */
  remove(conversationId: number) {
    return request<void>(`/api/conversations/${conversationId}`, { method: "DELETE" });
  },
};

export const runs = {
  /**
   * Answer the approval card a run paused on, with any values the person fixed on a confirm card.
   * The run carries on in the background, so the reply is then read with `followRun`. A 409 means
   * the card was already answered or has expired, and its `detail` says which.
   */
  decide(runId: number, approvalId: number, decision: ApprovalDecision, edits?: ApprovalEdits) {
    return request<RunResponse>(`/api/runs/${runId}/approvals/${approvalId}`, {
      method: "POST",
      body: JSON.stringify(edits ? { decision, edits } : { decision }),
    });
  },
};

export const auth = {
  /** Create an account. The backend signs the new person in at once by setting the cookie. */
  signUp(name: string, email: string, password: string) {
    return request<CurrentUser>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    });
  },

  /** Check the email and password. A wrong pair answers 401 "Invalid email or password". */
  signIn(email: string, password: string) {
    return request<CurrentUser>("/api/auth/signin", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  /** Clear the session cookie. */
  signOut() {
    return request<void>("/api/auth/signout", { method: "POST" });
  },

  /** Who the cookie belongs to. Answers 401 when nobody is signed in. */
  me(signal?: AbortSignal) {
    return request<CurrentUser>("/api/auth/me", { signal });
  },
};

export const voice = {
  /**
   * Turn one recording from the chat mic into text. The backend never saves the audio, and
   * answers empty text when nothing was said. Hindi comes back in English letters.
   */
  transcribe(audio: Blob) {
    const form = new FormData();

    form.append('audio', audio, 'speech');

    return request<{ text: string }>('/api/voice/transcribe', { method: 'POST', body: form });
  },
};

export const documents = {
  /**
   * Send one file to be read. Answered once it is parsed and checked, or waiting for a password,
   * an OK for the model, or columns, or failed with a reason. The same file again answers the earlier upload with `duplicate` set.
   */
  upload(file: File) {
    const form = new FormData();

    form.append("file", file);

    return request<DocumentView>("/api/documents", { method: "POST", body: form });
  },

  /** One upload with its sheet notes, questions and rows. */
  get(documentId: number) {
    return request<DocumentView>(`/api/documents/${documentId}`);
  },

  /** Every table a file can fill, with each field and its kind, for the mapping step. */
  fields() {
    return request<ImportFields>("/api/documents/fields");
  },

  /** Stocks and funds for a name being typed, closest first. */
  searchInstruments(query: string, signal?: AbortSignal) {
    return request<InstrumentChoice[]>(`/api/documents/instruments/search?q=${encodeURIComponent(query)}`, { signal });
  },

  /** Confirm the mapping of an unknown file; sheets left out keep the model's proposal. */
  confirmMapping(documentId: number, sheets: SheetChoice[]) {
    return request<DocumentView>(`/api/documents/${documentId}/mapping`, {
      method: "POST",
      body: JSON.stringify({ sheets }),
    });
  },

  /** Save answers to row questions. The document comes back checked again. */
  answer(documentId: number, answers: QuestionAnswer[]) {
    return request<DocumentView>(`/api/documents/${documentId}/answers`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    });
  },

  /** Change fields of one row, or pick its stock or fund. */
  editRow(documentId: number, rowId: number, edit: RowEdit) {
    return request<DocumentView>(`/api/documents/${documentId}/rows/${rowId}`, {
      method: "PATCH",
      body: JSON.stringify(edit),
    });
  },

  /** Read a locked PDF with its password. The password is used once and never saved. */
  unlock(documentId: number, password: string) {
    return request<DocumentView>(`/api/documents/${documentId}/password`, {
      method: "POST",
      body: JSON.stringify({ password }),
    });
  },

  /** Let the model read the pages only it can read, with the password again for a locked PDF. */
  allowModel(documentId: number, password?: string) {
    return request<DocumentView>(`/api/documents/${documentId}/read-pages`, {
      method: "POST",
      body: JSON.stringify(password ? { password } : {}),
    });
  },

  /** Give every row missing an as-of date this date, such as all holdings of a broker export. */
  setAsOfDate(documentId: number, asOfDate: string) {
    return request<DocumentView>(`/api/documents/${documentId}/as-of-date`, {
      method: "POST",
      body: JSON.stringify({ as_of_date: asOfDate }),
    });
  },

  /** Take one row out of this import so it is never written. Saved records are not touched. */
  removeRow(documentId: number, rowId: number) {
    return request<DocumentView>(`/api/documents/${documentId}/rows/${rowId}`, { method: "DELETE" });
  },

  /** Bring back a row taken out of this import. */
  restoreRow(documentId: number, rowId: number) {
    return request<DocumentView>(`/api/documents/${documentId}/rows/${rowId}/restore`, { method: "POST" });
  },

  /** Import anyway after seeing the rows do not add up to the file's totals. Asked again if that changes. */
  acceptTotals(documentId: number) {
    return request<DocumentView>(`/api/documents/${documentId}/accept-totals`, { method: "POST" });
  },

  /** Write every ready row into the person's records. */
  approve(documentId: number) {
    return request<ApprovalOutcome>(`/api/documents/${documentId}/approve`, { method: "POST" });
  },

  /** Undo everything this upload wrote, or nothing when a record changed after the import. */
  undo(documentId: number) {
    return request<DocumentView>(`/api/documents/${documentId}/undo`, { method: "POST" });
  },
};

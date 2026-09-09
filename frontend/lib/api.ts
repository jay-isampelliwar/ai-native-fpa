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
 * The user id is passed explicitly rather than read from a module-level singleton. Phase 1 has no
 * tokens, and threading it through makes the eventual move to a session obvious: this is the only
 * file that changes.
 *
 * There is no `planner` client here. The chat is one streaming endpoint, read by `lib/stream.ts`
 * through `fetch` directly because it is a POST that returns server-sent events rather than JSON.
 * The calls that used to sit here - send, approve, list, reopen and delete a conversation - were
 * removed with the endpoints behind them, and come back with the features that need them.
 *
 * Nothing here caches. Financial figures shown to a user must be the ones the backend just computed,
 * and a stale surplus rendered as current is exactly the failure the whole backend design avoids.
 */

import type {
  AlertsResponse,
  CommitResponse,
  GoalRead,
  HoldingsSummary,
  ImportRead,
  MappingProposal,
  MappingSheet,
  RecordCreated,
  StagedRow,
  StagedRowsPage,
  Workspace,
} from "@/lib/types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
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

  if (!response.ok) {
    let detail = response.statusText;

    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
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

export const users = {
  /**
   * Claim an id before anything is written against it.
   *
   * Idempotent, and called on every visit rather than only on the first: the id lives in this
   * browser's local storage, so a person who has one has no other way of telling the backend they
   * exist. Without it the row every record table points at is never created, and the failure surfaces
   * at a commit rather than at the gate where the id was typed.
   */
  register(userId: number) {
    return request<{ id: number; display_name: string; created: boolean }>("/api/v1/users", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    });
  },
};

export const documents = {
  upload(userId: number, file: File) {
    const form = new FormData();
    form.append("user_id", String(userId));
    form.append("file", file);

    return request<ImportRead>("/api/v1/documents", {
      method: "POST",
      body: form,
    });
  },

  read(userId: number, importId: string) {
    return request<ImportRead>(`/api/v1/documents/${importId}?user_id=${userId}`);
  },

  rows(userId: number, importId: string) {
    return request<StagedRowsPage>(
      `/api/v1/documents/${importId}/rows?user_id=${userId}`,
    );
  },

  correctRow(
    userId: number,
    importId: string,
    rowId: string,
    changes: Record<string, string>,
  ) {
    return request<StagedRow>(
      `/api/v1/documents/${importId}/rows/${rowId}?user_id=${userId}`,
      { method: "PATCH", body: JSON.stringify(changes) },
    );
  },

  decideRow(
    userId: number,
    importId: string,
    rowId: string,
    status: "accepted" | "rejected" | "pending",
  ) {
    return request<StagedRow>(
      `/api/v1/documents/${importId}/rows/${rowId}/decision?user_id=${userId}`,
      { method: "POST", body: JSON.stringify({ status }) },
    );
  },

  decideAll(
    userId: number,
    importId: string,
    status: "accepted" | "rejected",
    onlyPending = true,
  ) {
    return request<StagedRowsPage>(
      `/api/v1/documents/${importId}/decision?user_id=${userId}`,
      {
        method: "POST",
        body: JSON.stringify({ status, only_pending: onlyPending }),
      },
    );
  },

  commit(userId: number, importId: string) {
    return request<CommitResponse>(
      `/api/v1/documents/${importId}/commit?user_id=${userId}`,
      { method: "POST" },
    );
  },

  proposeMapping(userId: number, importId: string) {
    return request<MappingProposal>(
      `/api/v1/documents/${importId}/mapping/propose?user_id=${userId}`,
      { method: "POST" },
    );
  },

  confirmMapping(
    userId: number,
    importId: string,
    provider: string,
    name: string,
    sheets: MappingSheet[],
  ) {
    return request<ImportRead>(
      `/api/v1/documents/${importId}/mapping/confirm`,
      {
        method: "POST",
        body: JSON.stringify({ user_id: userId, provider, name, sheets }),
      },
    );
  },
};

export const assets = {
  holdings(userId: number) {
    return request<HoldingsSummary>(`/api/v1/assets/holdings?user_id=${userId}`);
  },
};

export const workspace = {
  read(userId: number) {
    return request<Workspace>(`/api/v1/workspace?user_id=${userId}`);
  },
};

export const alerts = {
  list(userId: number) {
    return request<AlertsResponse>(`/api/v1/alerts?user_id=${userId}`);
  },
};

export const goals = {
  list(userId: number) {
    return request<GoalRead[]>(`/api/v1/goals?user_id=${userId}`);
  },

  create(userId: number, body: Record<string, unknown>) {
    return request<RecordCreated>("/api/v1/goals", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, ...body }),
    });
  },
};

export const records = {
  createIncome(userId: number, body: Record<string, unknown>) {
    return request<RecordCreated>("/api/v1/records/income", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, ...body }),
    });
  },

  createExpense(userId: number, body: Record<string, unknown>) {
    return request<RecordCreated>("/api/v1/records/expenses", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, ...body }),
    });
  },

  createLiability(userId: number, body: Record<string, unknown>) {
    return request<RecordCreated>("/api/v1/records/liabilities", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, ...body }),
    });
  },

  createEmi(userId: number, body: Record<string, unknown>) {
    return request<RecordCreated>("/api/v1/records/emis", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, ...body }),
    });
  },

  createSip(userId: number, body: Record<string, unknown>) {
    return request<RecordCreated>("/api/v1/records/sips", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, ...body }),
    });
  },
};

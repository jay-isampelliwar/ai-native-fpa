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
 * There is one call left. The chat does not appear here because it is a POST that returns
 * server-sent events rather than JSON, so `lib/stream.ts` reads it from `fetch` directly. The
 * clients that used to sit here - planner, documents, records, goals, assets, alerts, workspace -
 * were removed with the endpoints behind them, and each comes back with the feature that needs it.
 *
 * Nothing here caches. Financial figures shown to a user must be the ones the backend just computed,
 * and a stale surplus rendered as current is exactly the failure the whole backend design avoids.
 */

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
   * later, against whatever first tries to write.
   */
  register(userId: number) {
    return request<{ id: number; display_name: string; created: boolean }>("/api/v1/users", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    });
  },
};

'use client';

/**
 * Who the current user is — an integer this browser holds, assigned on first visit.
 *
 * The backend has no tokens yet by deliberate decision: the product being proven
 * is the planner, not the login. Identity is therefore a number in local storage,
 * and this module is the only place that knows it, which is what makes replacing
 * it with a real session a change to one file.
 *
 * Nothing asks for it. An earlier build showed a gate that made a person type an
 * id before they could see anything, which is a strange thing to ask of someone
 * who has no account to identify. A demo id is assigned silently instead, and the
 * first screen is the product.
 *
 * Reads are wrapped because storage throws rather than returning null in real
 * situations — a private window with site data blocked, or an embedded context.
 * When it throws, the demo id is used for the session without being persisted,
 * so the app still works and simply forgets by the next visit.
 */

const STORAGE_KEY = 'mosaic.user_id';

/** Where assigned ids start. One per browser, not one per person. */
const DEMO_USER_ID = 1;

const listeners = new Set<() => void>();

/** Held in memory as well, so a browser that cannot persist still stays consistent. */
let current: number | null = null;

function announce(): void {
  for (const listener of listeners) listener();
}

export function subscribeToUserId(listener: () => void): () => void {
  listeners.add(listener);

  window.addEventListener('storage', listener);

  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', listener);
  };
}

/** What the server renders with: nobody, because storage does not exist there. */
export function serverUserId(): number | null {
  return null;
}

/**
 * The id for this browser, assigning one on the first call.
 *
 * `useSyncExternalStore` calls this on every render and compares the result, so it
 * has to return the same number each time rather than assigning a fresh one — the
 * cached `current` is what guarantees that.
 */
export function readUserId(): number | null {
  if (current !== null) return current;

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = Number(raw);

    if (raw && Number.isInteger(parsed) && parsed > 0) {
      current = parsed;
      return current;
    }

    window.localStorage.setItem(STORAGE_KEY, String(DEMO_USER_ID));
  } catch {
    // Storage is unavailable; the id lives for this session only.
  }

  current = DEMO_USER_ID;

  return current;
}

/** Switch to another id, for testing a different backend thread. */
export function writeUserId(userId: number): void {
  current = userId;

  try {
    window.localStorage.setItem(STORAGE_KEY, String(userId));
  } catch {
    // Remembered for this session only.
  }

  announce();
}

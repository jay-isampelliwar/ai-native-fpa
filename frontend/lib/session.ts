"use client";

/**
 * Who the current user is, which in this phase is an integer they type once.
 *
 * The backend has no tokens yet by deliberate decision - the product being proven is the planner, not
 * the login - so identity is a number kept in local storage. This module is the only place that knows
 * that, which is what makes replacing it with a real session a change to one file.
 *
 * Reads are wrapped because storage throws rather than returning null in a few real situations: a
 * private window with site data blocked, or an embedded context. A financial app that fails to render
 * because it could not read a preference is worse than one that asks for the id again.
 *
 * There is no default user. Guessing an id would show one person's portfolio to whoever opened the
 * app, and a blank state asking who you are is the honest alternative.
 *
 * Storage is exposed as something subscribable rather than as two bare functions, so a component can
 * read it with `useSyncExternalStore` instead of copying it into state inside an effect. That is not
 * a style preference: it is what keeps the server render and the hydration pass agreeing, and it also
 * makes a second tab that switches user propagate here rather than leaving two tabs disagreeing about
 * whose money is on screen.
 */

const STORAGE_KEY = "fpa.user_id";

const listeners = new Set<() => void>();

/** Notify every reader that the stored id changed, including tabs other than the one that wrote. */
function announce(): void {
  for (const listener of listeners) listener();
}

export function subscribeToUserId(listener: () => void): () => void {
  listeners.add(listener);

  window.addEventListener("storage", listener);

  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

/** What the server renders with: nobody, because storage does not exist there. */
export function serverUserId(): number | null | undefined {
  return undefined;
}

export function readUserId(): number | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);

    if (!raw) return null;

    const parsed = Number(raw);

    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
  } catch {
    return null;
  }
}

export function writeUserId(userId: number): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, String(userId));
  } catch {
    // A viewer who cannot persist their id simply enters it again next visit.
  }

  announce();
}

export function clearUserId(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to recover from; the id was never persisted.
  }

  announce();
}

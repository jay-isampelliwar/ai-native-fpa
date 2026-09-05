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
 */

const STORAGE_KEY = "fpa.user_id";

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
}

export function clearUserId(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to recover from; the id was never persisted.
  }
}

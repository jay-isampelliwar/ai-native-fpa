'use client';

/**
 * Who is signed in, as one small store every component reads the same way.
 *
 * The real proof of identity is the httpOnly cookie, which page scripts cannot read. So this store
 * learns the user by asking `GET /api/auth/me` once, and keeps the answer in memory. Sign-in and
 * sign-up hand the user in directly, so they do not need a second call.
 *
 * `loading` is what the server renders and what the first client render shows, so the screen never
 * flashes the sign-in page for someone who is already signed in.
 */

import { useEffect, useSyncExternalStore } from 'react';

import { auth, onUnauthorized } from '@/lib/api';
import type { CurrentUser } from '@/lib/types';

export type Session =
  | { status: 'loading' }
  | { status: 'signed-out' }
  | { status: 'signed-in'; user: CurrentUser };

const LOADING: Session = { status: 'loading' };

const listeners = new Set<() => void>();

let current: Session = LOADING;

/** The one `/me` call in flight or finished, so many components asking cause one request. */
let loading: Promise<void> | null = null;

function set(next: Session): void {
  current = next;

  for (const listener of listeners) listener();
}

onUnauthorized(() => {
  loading = Promise.resolve();

  set({ status: 'signed-out' });
});

function subscribe(listener: () => void): () => void {
  listeners.add(listener);

  return () => {
    listeners.delete(listener);
  };
}

function read(): Session {
  return current;
}

function serverRead(): Session {
  return LOADING;
}

/** Ask the backend who the cookie belongs to, once per page load. */
export function loadSession(): Promise<void> {
  if (loading) return loading;

  loading = auth
    .me()
    .then((user) => set({ status: 'signed-in', user }))
    .catch(() => set({ status: 'signed-out' }));

  return loading;
}

/** Store the user that sign-in or sign-up just returned. */
export function signedIn(user: CurrentUser): void {
  loading = Promise.resolve();

  set({ status: 'signed-in', user });
}

/** End the session on the backend, then forget the user here. */
export async function signOut(): Promise<void> {
  try {
    await auth.signOut();
  } catch {
    // The cookie may already be gone; this browser forgets the user either way.
  }

  loading = Promise.resolve();

  set({ status: 'signed-out' });
}

/** The current session, loading it on first use. */
export function useSession(): Session {
  const session = useSyncExternalStore(subscribe, read, serverRead);

  useEffect(() => {
    void loadSession();
  }, []);

  return session;
}

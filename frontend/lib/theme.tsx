'use client';

import { createContext, useCallback, useContext, useSyncExternalStore, type ReactNode } from 'react';

/**
 * Light and dark, chosen by the reader and remembered in this browser.
 *
 * The chosen theme lives in one place only: the `data-theme` attribute on the root
 * element, which is what the token blocks in `globals.css` key off. React does not
 * keep a second copy of it — it subscribes to the attribute and reads it. That is
 * why this is an external store rather than a `useState` synchronised by an effect:
 * a copy would have to be kept in step with the DOM, and the moment the two
 * disagree the page is one colour while the app believes it is the other.
 *
 * Dark is the default and the OS preference is not consulted: the product opens
 * dark for everyone who has not said otherwise, rather than opening differently
 * depending on the machine. A stored choice is the only thing that changes it.
 *
 * The attribute is set before first paint by the script below, so a reader who
 * chose light never sees a frame of dark. React cannot do that from an effect —
 * effects run after paint — which is the whole reason the script exists.
 *
 * Storage access is wrapped: a private window with site data blocked throws on
 * read rather than returning null, and losing the session over a colour preference
 * would be an absurd failure for a financial dashboard.
 */

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'mosaic.theme';

/** Broadcast so every subscriber re-reads the attribute after a change. */
const CHANGE_EVENT = 'mosaic:theme';

/** Runs before paint, from `layout.tsx`. Kept beside the reader so both agree. */
export const THEME_BOOTSTRAP = `
(function () {
  try {
    var stored = localStorage.getItem('${STORAGE_KEY}');
    var theme = stored === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', theme);
  } catch (error) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
})();
`;

function subscribe(listener: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, listener);
  // Another tab switching theme should move this one too.
  window.addEventListener('storage', listener);

  return () => {
    window.removeEventListener(CHANGE_EVENT, listener);
    window.removeEventListener('storage', listener);
  };
}

/** The truth, read straight off the element the bootstrap script already set. */
function readTheme(): Theme {
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}

/** What the server renders with, and what the markup therefore says. */
function serverTheme(): Theme {
  return 'dark';
}

interface ThemeContextValue {
  theme: Theme;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);

  if (!value) throw new Error('useTheme was called outside ThemeProvider');

  return value;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useSyncExternalStore(subscribe, readTheme, serverTheme);

  const toggle = useCallback(() => {
    const next: Theme = readTheme() === 'dark' ? 'light' : 'dark';

    document.documentElement.setAttribute('data-theme', next);

    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // A reader who cannot persist the choice simply makes it again next visit.
    }

    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>;
}

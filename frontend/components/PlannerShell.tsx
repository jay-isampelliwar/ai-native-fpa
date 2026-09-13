'use client';

import { LayoutDashboard, MessageSquare } from 'lucide-react';
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

import { readUserId, serverUserId, subscribeToUserId } from '@/lib/session';
import { ThemeProvider } from '@/lib/theme';
import ChatWorkspace from '@/components/chat/ChatWorkspace';
import FinancialDashboard from '@/components/dashboard/FinancialDashboard';

/**
 * The two regions, and nothing between them but a divider.
 *
 * There is no icon rail. The doc corrects the reference on exactly this point: the
 * application has a conversation on the left and a dashboard on the right, the chat
 * begins at the left edge of the window, and there is no third column or global
 * navigation. There is nowhere else to go, so there is nothing to navigate to.
 *
 * Each pane is mounted exactly once, and the two layouts — the desktop split and
 * the phone's tabs — are the same elements shown differently by CSS. Rendering the
 * panes twice, once per layout, is the obvious way to write this and it is wrong
 * twice over: the chat's `id`s appear in the document twice, so a label points at
 * whichever copy comes first, and each copy registers its own user and holds its
 * own conversation. Hiding with a class instead means switching tabs or crossing
 * the breakpoint never unmounts anything, which is also what preserves the chat.
 *
 * The split is draggable between 34% and 46%, which the doc gives as the sensible
 * range, and starts at 40. During a drag the width is written to a CSS variable
 * rather than to React state: state would re-render both panes — including a chart
 * — on every frame. React is told once, on release.
 *
 * Identity is resolved here, once, and handed to both panes. The chat is keyed on
 * it, so switching user unmounts the conversation and mounts a fresh one — which is
 * the correct behaviour and also the cheapest: a reset function would have to be
 * kept in step with every piece of state the chat gains later, and the first one
 * anybody forgets leaves the previous person's turns on screen under a new id.
 *
 * The viewport is measured only to choose ARIA roles. A pane that is a `tabpanel`
 * on a phone is just a region on a desktop, and no structure depends on the
 * answer, so a wrong first guess costs an attribute rather than a remount.
 */

const MIN = 34;
const MAX = 46;
const DEFAULT = 40;

const DESKTOP = '(min-width: 768px)';

type MobileTab = 'chat' | 'overview';

function subscribeToViewport(listener: () => void): () => void {
  const query = window.matchMedia(DESKTOP);

  query.addEventListener('change', listener);

  return () => query.removeEventListener('change', listener);
}

/** Server-side there is no viewport; desktop is the layout the markup describes. */
function useIsDesktop(): boolean {
  return useSyncExternalStore(
    subscribeToViewport,
    () => window.matchMedia(DESKTOP).matches,
    () => true,
  );
}

export default function PlannerShell() {
  const [width, setWidth] = useState(DEFAULT);
  const [tab, setTab] = useState<MobileTab>('chat');

  const desktop = useIsDesktop();
  const userId = useSyncExternalStore(subscribeToUserId, readUserId, serverUserId);

  const frame = useRef<HTMLDivElement>(null);
  const handle = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  /** Paint a width without telling React, so a drag does not re-render the charts. */
  const paint = useCallback((next: number) => {
    frame.current?.style.setProperty('--chat-width', `${next}%`);
  }, []);

  useEffect(() => {
    paint(width);
  }, [width, paint]);

  useEffect(() => {
    function onMove(event: PointerEvent) {
      if (!dragging.current || !frame.current) return;

      const bounds = frame.current.getBoundingClientRect();
      const ratio = ((event.clientX - bounds.left) / bounds.width) * 100;

      paint(Math.min(MAX, Math.max(MIN, ratio)));
    }

    function onUp() {
      if (!dragging.current) return;

      dragging.current = false;
      document.body.removeAttribute('data-resizing');
      handle.current?.removeAttribute('data-dragging');

      // Read back what was painted, so React's copy matches the DOM exactly once.
      const parsed = Number.parseFloat(frame.current?.style.getPropertyValue('--chat-width') ?? '');

      if (!Number.isNaN(parsed)) setWidth(parsed);
    }

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);

    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
  }, [paint]);

  function startDrag() {
    dragging.current = true;
    document.body.setAttribute('data-resizing', 'true');
    handle.current?.setAttribute('data-dragging', 'true');
  }

  /** Arrow keys move the divider too, in steps a keyboard user can aim with. */
  function onHandleKey(event: React.KeyboardEvent) {
    const step = event.shiftKey ? 4 : 1;

    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      setWidth((current) => Math.max(MIN, current - step));
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      setWidth((current) => Math.min(MAX, current + step));
    } else if (event.key === 'Home') {
      event.preventDefault();
      setWidth(DEFAULT);
    }
  }

  /** On a phone the inactive pane is hidden; on a desktop both are always shown. */
  const paneRole = (pane: MobileTab) =>
    desktop
      ? ({ 'aria-label': pane === 'chat' ? 'Conversation' : 'Financial overview' } as const)
      : ({
          role: 'tabpanel',
          id: `panel-${pane}`,
          'aria-labelledby': `tab-${pane}`,
        } as const);

  return (
    <ThemeProvider>
      <div
        ref={frame}
        className="flex h-dvh min-h-0 flex-col"
        style={{ ['--chat-width' as string]: `${DEFAULT}%` }}
      >
        <div className="flex min-h-0 flex-1">
          <main
            {...paneRole('chat')}
            className={`min-h-0 w-full shrink-0 md:w-[var(--chat-width)] md:border-r md:border-line ${
              tab === 'chat' ? '' : 'max-md:hidden'
            }`}
          >
            <ChatWorkspace key={userId ?? 'anonymous'} userId={userId} onResetWidth={() => setWidth(DEFAULT)} />
          </main>

          <div
            ref={handle}
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize the conversation panel"
            aria-valuenow={Math.round(width)}
            aria-valuemin={MIN}
            aria-valuemax={MAX}
            tabIndex={0}
            onPointerDown={startDrag}
            onKeyDown={onHandleKey}
            onDoubleClick={() => setWidth(DEFAULT)}
            className="split-handle hidden md:block"
          />

          <main
            {...paneRole('overview')}
            className={`min-h-0 w-full flex-1 md:w-auto ${
              tab === 'overview' ? '' : 'max-md:hidden'
            }`}
          >
            <FinancialDashboard userId={userId} />
          </main>
        </div>

        <nav
          role="tablist"
          aria-label="Sections"
          className="flex flex-none items-center gap-1 border-t border-line bg-background px-3 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] md:hidden"
        >
          <Tab id="chat" current={tab} onSelect={setTab} icon={<MessageSquare size={15} />}>
            Chat
          </Tab>
          <Tab id="overview" current={tab} onSelect={setTab} icon={<LayoutDashboard size={15} />}>
            Overview
          </Tab>
        </nav>
      </div>
    </ThemeProvider>
  );
}

function Tab({
  id,
  current,
  onSelect,
  icon,
  children,
}: {
  id: MobileTab;
  current: MobileTab;
  onSelect: (tab: MobileTab) => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  const active = current === id;

  return (
    <button
      type="button"
      role="tab"
      id={`tab-${id}`}
      aria-selected={active}
      aria-controls={`panel-${id}`}
      onClick={() => onSelect(id)}
      className="flex flex-1 items-center justify-center gap-1.5 rounded-xl py-2.5 text-[12.5px] font-semibold transition"
      style={
        active
          ? { background: 'var(--accent-soft)', color: 'var(--accent)' }
          : { color: 'var(--text-secondary)' }
      }
    >
      <span aria-hidden="true">{icon}</span>
      {children}
    </button>
  );
}

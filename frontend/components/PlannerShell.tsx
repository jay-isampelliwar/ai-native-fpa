'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import { useSession } from '@/lib/session';
import { ThemeProvider } from '@/lib/theme';
import ChatWorkspace from '@/components/chat/ChatWorkspace';
import HistoryPanel from '@/components/chat/HistoryPanel';

/**
 * The list of past chats on the left, with the open chat beside it.
 *
 * The dashboard is hidden for now. Its components are kept in `components/dashboard`
 * and come back by rendering `FinancialDashboard` here again.
 *
 * On a wide screen the history list is a fixed column on the left. On a smaller one
 * it is a drawer that slides in from the left, opened from the chat header's History
 * button.
 *
 * Which chat is open lives here. Picking a chat or pressing New Chat changes the
 * chat pane's key, so it mounts fresh and loads only that conversation. When the
 * pane itself starts a new chat, only the highlighted id changes, not the key, so
 * the reply being written is not thrown away.
 *
 * `historyVersion` is bumped whenever the pane reports activity, which makes the
 * list fetch again: a new chat appears in it, and a chat that just got a reply moves
 * to the top.
 *
 * While the chat has a form open, the history list hides so the chat and the form each get half.
 *
 * The layout follows ChatGPT and Claude: a full-height list on the left edge, and the chat filling
 * the rest of the screen, with its text in one centred column. Nothing is zoomed on a big screen;
 * the column simply keeps its width and the space around it stays empty.
 *
 * Nothing renders until the session is known. Someone who is not signed in is sent
 * to `/signin` instead.
 */
export default function PlannerShell() {
  const router = useRouter();
  const session = useSession();

  const [opened, setOpened] = useState<{ key: number; conversationId: number | null }>({
    key: 0,
    conversationId: null,
  });
  const [activeId, setActiveId] = useState<number | null>(null);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [drawer, setDrawer] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const onFormChange = useCallback((open: boolean) => setFormOpen(open), []);

  function open(conversationId: number | null) {
    setDrawer(false);

    if (conversationId !== null && conversationId === activeId) return;

    setActiveId(conversationId);
    setOpened((current) => ({ key: current.key + 1, conversationId }));
  }

  function onActivity(conversationId: number) {
    setActiveId(conversationId);
    setHistoryVersion((version) => version + 1);
  }

  useEffect(() => {
    if (session.status === 'signed-out') router.replace('/signin');
  }, [session.status, router]);

  if (session.status !== 'signed-in') {
    return <div className="h-dvh bg-background" aria-busy="true" />;
  }

  const userId = session.user.id;

  const history = (onClose?: () => void) => (
    <HistoryPanel
      activeId={activeId}
      version={historyVersion}
      onSelect={(id) => open(id)}
      onNewChat={() => open(null)}
      onDeleted={(id) => {
        if (id === activeId) open(null);
      }}
      onClose={onClose}
    />
  );

  return (
    <ThemeProvider>
      <div className="h-dvh bg-background">
        <div className="flex h-full min-h-0">
          <aside
            aria-label="Chat history"
            className={`hidden min-h-0 w-[272px] flex-none overflow-hidden border-r border-[var(--pane-border)] bg-panel-subtle ${formOpen ? '' : 'lg:block'}`}
          >
            {history()}
          </aside>

          <div className="min-h-0 min-w-0 flex-1">
            <ChatWorkspace
              key={`${userId}-${opened.key}`}
              userId={userId}
              openConversationId={opened.conversationId}
              onActivity={onActivity}
              onShowHistory={() => setDrawer(true)}
              onFormChange={onFormChange}
            />
          </div>

          {drawer && (
            <div className="fixed inset-0 z-50 lg:hidden">
              <button
                type="button"
                aria-label="Close history"
                onClick={() => setDrawer(false)}
                className="absolute inset-0 bg-black/50 backdrop-blur-sm"
              />

              <aside
                aria-label="Chat history"
                className="absolute top-0 bottom-0 left-0 w-[min(300px,calc(100%-3rem))] overflow-hidden border-r border-[var(--pane-border)] bg-panel-subtle"
              >
                {history(() => setDrawer(false))}
              </aside>
            </div>
          )}
        </div>
      </div>
    </ThemeProvider>
  );
}

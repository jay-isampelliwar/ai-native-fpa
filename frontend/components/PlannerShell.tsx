'use client';

import { useState, useSyncExternalStore } from 'react';

import { readUserId, serverUserId, subscribeToUserId } from '@/lib/session';
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
 */
export default function PlannerShell() {
  const userId = useSyncExternalStore(subscribeToUserId, readUserId, serverUserId);

  const [opened, setOpened] = useState<{ key: number; conversationId: number | null }>({
    key: 0,
    conversationId: null,
  });
  const [activeId, setActiveId] = useState<number | null>(null);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [drawer, setDrawer] = useState(false);

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

  const history = (onClose?: () => void) => (
    <HistoryPanel
      activeId={activeId}
      version={historyVersion}
      onSelect={(id) => open(id)}
      onNewChat={() => open(null)}
      onClose={onClose}
    />
  );

  return (
    <ThemeProvider>
      <div className="app-backdrop flex h-dvh min-h-0 gap-3 p-2 md:p-3">
        <aside aria-label="Chat history" className="glass-pane hidden min-h-0 w-[320px] flex-none overflow-hidden lg:block">
          {history()}
        </aside>

        <main aria-label="Conversation" className="glass-pane min-h-0 min-w-0 flex-1 overflow-hidden">
          <ChatWorkspace
            key={`${userId ?? 'anonymous'}-${opened.key}`}
            userId={userId}
            openConversationId={opened.conversationId}
            onActivity={onActivity}
            onShowHistory={() => setDrawer(true)}
          />
        </main>

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
              className="glass-pane absolute top-2 bottom-2 left-2 w-[min(320px,calc(100%-1rem))] overflow-hidden"
            >
              {history(() => setDrawer(false))}
            </aside>
          </div>
        )}
      </div>
    </ThemeProvider>
  );
}

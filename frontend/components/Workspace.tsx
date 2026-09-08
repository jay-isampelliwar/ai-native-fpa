'use client';

import { useEffect, useState } from 'react';

import { BlockRenderer } from '@/components/blocks';
import { useUser } from '@/components/Shell';
import { workspace as workspaceApi } from '@/lib/api';
import { useRecordsVersion } from '@/lib/records';
import type { Workspace as WorkspaceData } from '@/lib/types';

/**
 * The standing view of what the planner knows, beside the conversation rather than inside it.
 *
 * A chat is the wrong shape for a figure someone wants to keep glancing at. An answer scrolls away,
 * and the surplus a person is reasoning about ends up four questions up the thread. This panel holds
 * the same typed blocks a skill returns and simply stays, so the conversation is where things are
 * asked and this is where they are.
 *
 * It shows everything currently computable rather than the last answer. A panel that followed the
 * conversation would take the portfolio away the moment someone asked about a goal, and a reader who
 * has to remember which question produced the current contents cannot use it as a reference.
 *
 * Sections arrive from the backend as a list and are rendered in order. Which sections exist is a
 * property of the data, not of this file: adding a widget server side makes it appear here without a
 * frontend change, and a section with nothing to show is absent rather than rendered with dashes.
 *
 * Before there is data the panel is the interview. Someone new sees which records are missing and
 * watches the list fill in as they answer, which is the only version of an empty state that does any
 * work.
 *
 * Refreshing is driven by the records-changed signal in `lib/records`, not by polling. The panel
 * reloads exactly when something wrote - a confirmed record, a committed import - and a timer would
 * either lag that or ask a question nobody needed answered every few seconds. Every figure here is
 * computed by the backend at read time, so a refetch is genuinely a recalculation rather than a cache
 * being refreshed; there is nothing stored that could disagree with the rows.
 *
 * The signal used to arrive as a prop from `Console`. It is subscribed to directly now, because this
 * panel is not the only reader any more and a parent threading a counter to each of them was a wire
 * that told you nothing about who was listening.
 */
export default function Workspace() {
  const userId = useUser();

  const version = useRecordsVersion();

  const [data, setData] = useState<WorkspaceData | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const next = await workspaceApi.read(userId);

        if (cancelled) return;

        setData(next);
        setFailed(false);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [userId, version]);

  if (failed) {
    return (
      <Frame>
        <p className="text-[12.5px] leading-5 text-[#8f4227]">
          I could not load your workspace. Check that the backend is running.
        </p>
      </Frame>
    );
  }

  if (!data) {
    return (
      <Frame>
        <div className="space-y-2">
          <div className="h-3 w-24 animate-pulse rounded bg-[#18312f]/8" />
          <div className="h-20 animate-pulse rounded-xl bg-[#18312f]/6" />
        </div>
      </Frame>
    );
  }

  const { readiness, sections } = data;

  return (
    <Frame>
      <div className="space-y-5">
        <Readiness readiness={readiness} />

        {sections.map((section) => (
          <section key={section.key} className="space-y-2">
            <div className="flex items-baseline justify-between gap-2">
              <h2 className="font-serif text-[17px] leading-tight tracking-[-0.01em] text-[#18312f]">
                {section.title}
              </h2>
              {section.subtitle && (
                <span className="shrink-0 font-mono text-[10.5px] text-[#a8b8b4]">
                  {section.subtitle}
                </span>
              )}
            </div>

            <BlockRenderer blocks={section.blocks} />
          </section>
        ))}
      </div>
    </Frame>
  );
}

/**
 * The checklist of what is still missing, which is the whole panel until there is data.
 *
 * It stays after the data arrives rather than disappearing. "What else could this answer if I gave it
 * more?" is a question people keep asking, and removing the answer once the first widget appears
 * makes the panel feel finished when it is not.
 */
function Readiness({ readiness }: { readiness: WorkspaceData['readiness'] }) {
  const entries = Object.entries(readiness.labels);

  return (
    <section className="rounded-2xl border border-[#18312f]/9 bg-white/70 p-4">
      <h2 className="font-serif text-[17px] leading-tight tracking-[-0.01em] text-[#18312f]">
        {readiness.has_any_records ? 'What I have' : 'To get started'}
      </h2>

      {!readiness.has_any_records && (
        <p className="mt-1 text-[12.5px] leading-5 text-[#4d6560]">
          Tell me on the right, or attach a statement. Nothing is stored until you confirm it.
        </p>
      )}

      <ul className="mt-3 space-y-1.5">
        {entries.map(([key, label]) => {
          const count = readiness.held[key] ?? 0;

          return (
            <li key={key} className="flex items-center gap-2.5">
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                  count > 0 ? 'bg-[#00947a]' : 'bg-[#18312f]/15'
                }`}
              />

              <span
                className={`flex-1 text-[12.5px] leading-5 ${
                  count > 0 ? 'text-[#18312f]' : 'text-[#8ba09c]'
                }`}
              >
                {label}
              </span>

              <span className="shrink-0 text-[11.5px] tabular-nums text-[#8ba09c]">
                {count > 0 ? count : 'needed'}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto">
      <div className="px-5 py-7">{children}</div>
    </div>
  );
}

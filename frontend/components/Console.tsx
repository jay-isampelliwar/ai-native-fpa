'use client';

import { useState } from 'react';

import ChatPanel from '@/components/ChatPanel';
import Workspace from '@/components/Workspace';

/**
 * The two halves of the product side by side: what the planner knows, and the conversation that changes it.
 *
 * The split exists because the two do different jobs. A conversation is a sequence - it is read once,
 * in order, and scrolls away - while a person's financial position is a state they want to look at
 * repeatedly. Putting the second inside the first meant the surplus someone was reasoning about
 * disappeared behind their next question.
 *
 * The chat is on the right because that is where the typing happens, and the thing being typed into
 * should not be the thing that moves when an answer arrives.
 *
 * The panel is refreshed by a counter rather than by polling. Only the chat knows when something
 * changed the records - a confirmed record, a committed import - so it says so, and the panel reloads
 * exactly then. A timer would either lag the change or ask a question nobody needed answered.
 *
 * Below the split's breakpoint the panel moves above the conversation rather than beside it. Two
 * columns in a phone's width gives neither enough room to be read, and the panel is what someone
 * wants to see first on arriving.
 */
export default function Console() {
  const [version, setVersion] = useState(0);

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <aside className="flex min-h-0 shrink-0 flex-col border-b border-[#18312f]/8 bg-[#f5f2e8]/40 lg:w-[min(42%,30rem)] lg:border-b-0 lg:border-r">
        <Workspace version={version} />
      </aside>

      <div className="flex min-h-0 flex-1 flex-col">
        <ChatPanel onRecordsChanged={() => setVersion((current) => current + 1)} />
      </div>
    </div>
  );
}

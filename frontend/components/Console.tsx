'use client';

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
 * The panel takes the larger share — sixty against forty. It holds four views now rather than one, and
 * a projection squeezed into thirty rem is a shape nobody can read; a conversation is text and narrows
 * gracefully, which a chart does not.
 *
 * This component used to hold a version counter and hand it down, because the chat was the only thing
 * that knew when the records had moved and the panel was the only thing that needed telling. Both
 * halves of that stopped being true — the portfolio and alerts pages want the same signal, and a
 * change can now come from more places in the chat — so the signal lives in `lib/records` and each
 * side talks to it directly. Nothing about when a refresh happens changed; what changed is that this
 * component is no longer a wire between two things that can find each other.
 *
 * Below the split's breakpoint the panel moves above the conversation rather than beside it. Two
 * columns in a phone's width gives neither enough room to be read, and the panel is what someone
 * wants to see first on arriving.
 */
export default function Console() {
  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <aside className="flex min-h-0 shrink-0 flex-col border-b border-[#18312f]/8 bg-[#f5f2e8]/40 lg:w-[60%] lg:border-b-0 lg:border-r">
        <Workspace />
      </aside>

      <div className="flex min-h-0 flex-1 flex-col">
        <ChatPanel />
      </div>
    </div>
  );
}

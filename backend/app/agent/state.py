"""What one chat turn carries through the graph.

``PlannerState`` extends ``MessagesState``, so ``messages`` arrives with the ``add_messages`` reducer
already on it: a node returns the one message it produced and the reducer appends it, rather than the
node rebuilding the list. That is also what lets the checkpointer hand the earlier turns of a thread
back on the next request.

``user_id`` and ``conversation_id`` are the only other fields, and they are the two the request has to
supply. The conversation id is the checkpointer's thread id as well, which is why it is state rather
than something the API keeps to itself.

``conversation_summary`` is ``NotRequired`` and nothing writes it yet. It is here for the point where
a long thread costs more to send than it is worth, and a summary replaces the turns before it.

The fields that used to be here - the resolved caller context, the run log of tool calls and blocks,
the denial reason, the pending approval - belonged to a planner that routed to skills and paused
writes for a person. Each returns with the feature that needs it, not before.
"""

from typing import NotRequired

from langgraph.graph import MessagesState


class PlannerState(MessagesState):

    """One chat turn: the thread's messages, who is asking, and which thread it is."""

    user_id: int
    conversation_id: str

    conversation_summary: NotRequired[str]

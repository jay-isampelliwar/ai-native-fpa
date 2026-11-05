import type { OrbState } from '@/lib/orb/engine';

/**
 * Which orb a tool step shows, by what the tool does.
 *
 * Tools that only read show `searching`, the goal check shows `weaving`, and every tool that
 * writes (add, update, delete, set, allocate) shows `composing`. A tool added later without an
 * entry here is treated as a write, the common case.
 */

const READ_TOOLS = new Set(['list_records', 'get_missing_sections']);

export function orbStateForTool(name: string): OrbState {
  if (READ_TOOLS.has(name)) return 'searching';
  if (name === 'check_goal_progress') return 'weaving';

  return 'composing';
}

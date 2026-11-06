/**
 * Splitting a reply's text at its card lines.
 *
 * The agent places a card by writing `{{card:<tool call id>}}` on its own line. The text around it
 * stays markdown, and each marker becomes the card the tool sent for that id. A marker whose card
 * never came is dropped, so the reader never sees the raw braces. While a reply streams, a marker
 * that is only half written is held back until it closes.
 */

export type Segment = { kind: 'text'; text: string } | { kind: 'card'; id: string };

const MARKER = /\{\{card:([^}\s]+)\}\}/g;

const PARTIAL = /\{\{(?:c(?:a(?:r(?:d(?::[^}\s]*\}?)?)?)?)?)?$/;

export function splitCards(text: string): Segment[] {
  const segments: Segment[] = [];
  let cursor = 0;

  for (const match of text.matchAll(MARKER)) {
    const before = text.slice(cursor, match.index);

    if (before.trim()) segments.push({ kind: 'text', text: before });

    segments.push({ kind: 'card', id: match[1] });
    cursor = match.index + match[0].length;
  }

  const rest = text.slice(cursor).replace(PARTIAL, '');

  if (rest.trim()) segments.push({ kind: 'text', text: rest });

  return segments;
}

/** The reply without its card lines, for copying as plain text. */
export function withoutCards(text: string): string {
  return text.replace(MARKER, '').replace(/\n{3,}/g, '\n\n').trim();
}

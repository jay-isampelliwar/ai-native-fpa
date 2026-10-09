import type { ReactNode } from 'react';

/**
 * The planner's answer, rendered rather than printed.
 *
 * The backend streams markdown - it is one model call answering in sentences,
 * and models write `**like this**`. Until now the chat put that string in a
 * `<p>` unchanged, so a reader asking about their salary was shown
 * `**Monthly Gross Salary** is ₹250,000` with the asterisks still in it. That is
 * not a cosmetic problem: the emphasis the model put on the figure is the part
 * that got lost, and the noise landed on the one line the reader came for.
 *
 * This is a deliberately small subset - paragraphs, the two kinds of list, a
 * heading, tables, a rule, bold, italic, inline code - because that is the whole
 * of what the planner actually emits. Tables were added once the planner began
 * answering portfolio questions with them; before that, every `|` row was joined
 * into one paragraph. A full markdown library would add a dependency and a
 * sanitiser's worth of risk to render images nothing sends.
 *
 * Nothing here interprets HTML. The model's text is only ever placed as text
 * nodes, so a reply that happens to contain a tag is shown, not run.
 *
 * Money is the one addition beyond markdown. A rupee figure is found and marked
 * so it can be set in tabular amber - on a screen about someone's finances the
 * numbers are what the eye should be able to find without reading, and the model
 * cannot be relied on to mark them itself.
 */

/** `₹250,000`, `₹ 1,20,000.50`, `₹12 lakh` — the shapes the planner actually writes. */
const AMOUNT = String.raw`₹\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:lakh|lakhs|crore|crores|L|Cr))?`;

const INLINE = new RegExp(
  ['`[^`]+`', String.raw`\*\*[^*]+\*\*`, String.raw`\*[^*\n]+\*`, AMOUNT].map((p) => `(?:${p})`).join('|'),
  'g',
);

/**
 * Split one line into text and the spans that carry formatting.
 *
 * Bold and italic are re-entered rather than treated as leaves, because the
 * model writes `**₹250,000**` constantly — the figure has to keep its colour
 * even when the emphasis is what wrapped it. The depth guard is what makes that
 * recursion terminate on input this function did not write.
 */
function inline(text: string, depth = 0): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let key = 0;

  for (const match of text.matchAll(INLINE)) {
    const token = match[0];
    const at = match.index;

    if (at > cursor) nodes.push(text.slice(cursor, at));
    cursor = at + token.length;

    if (token.startsWith('`')) {
      nodes.push(<code key={key++}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith('**')) {
      const inner = token.slice(2, -2);
      nodes.push(<strong key={key++}>{depth < 3 ? inline(inner, depth + 1) : inner}</strong>);
    } else if (token.startsWith('*')) {
      const inner = token.slice(1, -1);
      nodes.push(<em key={key++}>{depth < 3 ? inline(inner, depth + 1) : inner}</em>);
    } else {
      nodes.push(
        <span className="amount" key={key++}>
          {token}
        </span>,
      );
    }
  }

  if (cursor < text.length) nodes.push(text.slice(cursor));

  return nodes;
}

const BULLET = /^\s*[-*•]\s+/;
const NUMBERED = /^\s*\d+[.)]\s+/;
const HEADING = /^\s*#{1,6}\s+/;
const TABLE_ROW = /^\s*\|/;
const TABLE_DIVIDER = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const RULE = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/;

type Align = 'left' | 'right' | 'center';

/** `| a | b |` → `['a', 'b']`. The outer pipes are optional in markdown, so both are trimmed. */
function cells(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

/** `:---` is left, `---:` is right, `:---:` is centre. Plain `---` is left. */
function alignments(divider: string): Align[] {
  return cells(divider).map((cell) =>
    cell.startsWith(':') && cell.endsWith(':') ? 'center' : cell.endsWith(':') ? 'right' : 'left',
  );
}

/**
 * Group the lines into blocks.
 *
 * Consecutive list items become one list, which is the only reason this needs a
 * pass over the lines at all rather than a map. A blank line between two items
 * is treated as still the same list — models emit those freely, and starting a
 * second `<ul>` there would double the leading space for no reason the reader
 * could see.
 */
type Block =
  | { kind: 'heading'; text: string }
  | { kind: 'para'; text: string }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'table'; head: string[]; align: Align[]; rows: string[][] }
  | { kind: 'rule' };

function blocks(source: string): Block[] {
  const out: Block[] = [];
  let paragraph: string[] = [];

  function flush() {
    if (paragraph.length) {
      out.push({ kind: 'para', text: paragraph.join(' ') });
      paragraph = [];
    }
  }

  for (const line of source.split('\n')) {
    const open = out.at(-1);

    if (!line.trim()) {
      flush();
      continue;
    }

    // A table is a run of `|` lines. The second line is the `|---|` divider, which only
    // sets alignment and is never drawn. While a reply streams, the table grows row by row.
    if (TABLE_ROW.test(line)) {
      flush();

      if (open?.kind === 'table') {
        if (TABLE_DIVIDER.test(line) && open.rows.length === 0) open.align = alignments(line);
        else open.rows.push(cells(line));
      } else {
        out.push({ kind: 'table', head: cells(line), align: [], rows: [] });
      }

      continue;
    }

    if (RULE.test(line)) {
      flush();
      out.push({ kind: 'rule' });
      continue;
    }

    if (HEADING.test(line)) {
      flush();
      out.push({ kind: 'heading', text: line.replace(HEADING, '') });
      continue;
    }

    const ordered = NUMBERED.test(line);

    if (ordered || BULLET.test(line)) {
      flush();

      const item = line.replace(ordered ? NUMBERED : BULLET, '');

      if (open?.kind === 'list' && open.ordered === ordered) open.items.push(item);
      else out.push({ kind: 'list', ordered, items: [item] });

      continue;
    }

    paragraph.push(line.trim());
  }

  flush();

  return out;
}

/**
 * The prose, and — while it is still arriving — a caret at the very end of it.
 *
 * The caret is appended to the last block's children rather than rendered after
 * the container. A block element placed after a paragraph sits on its own line,
 * so the cursor would detach from the sentence it belongs to every time the
 * model happened to finish a line; inside the last block it stays where a person
 * writing would leave it.
 */
export default function Reply({ text, streaming = false }: { text: string; streaming?: boolean }) {
  const parsed = blocks(text);
  const last = parsed.length - 1;
  const caret = <span className="caret" key="caret" aria-hidden="true" />;

  return (
    <div className="reply text-[14px] leading-[1.68]">
      {parsed.map((block, index) => {
        const tail = streaming && index === last;

        if (block.kind === 'heading') {
          return (
            <h3 key={index}>
              {inline(block.text)}
              {tail && caret}
            </h3>
          );
        }

        if (block.kind === 'rule') return <hr key={index} />;

        if (block.kind === 'table') {
          const lastRow = block.rows.length - 1;

          return (
            <div key={index} className="reply-table quiet-scroll">
              <table>
                <thead>
                  <tr>
                    {block.head.map((cell, at) => (
                      <th key={at} style={{ textAlign: block.align[at] ?? 'left' }}>
                        {inline(cell)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, rowAt) => (
                    <tr key={rowAt}>
                      {row.map((cell, at) => (
                        <td key={at} style={{ textAlign: block.align[at] ?? 'left' }}>
                          {inline(cell)}
                          {tail && rowAt === lastRow && at === row.length - 1 && caret}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }

        if (block.kind === 'para') {
          return (
            <p key={index}>
              {inline(block.text)}
              {tail && caret}
            </p>
          );
        }

        const items = block.items.map((item, at) => (
          <li key={at}>
            {inline(item)}
            {tail && at === block.items.length - 1 && caret}
          </li>
        ));

        return block.ordered ? <ol key={index}>{items}</ol> : <ul key={index}>{items}</ul>;
      })}
    </div>
  );
}

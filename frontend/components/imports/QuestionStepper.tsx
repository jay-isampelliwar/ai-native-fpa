'use client';

import { ChevronLeft, ChevronRight, HelpCircle, Loader2 } from 'lucide-react';
import { useState } from 'react';

import { rowTitle } from '@/lib/imports';
import type { ImportQuestion, ImportRowView } from '@/lib/types';

/**
 * The open questions of one upload, one at a time, as "1 of 26".
 *
 * The code asks only where it was not sure, so every choice here comes from the person. Picking a
 * choice saves it and moves to the next open question; Back and Next move without answering.
 */

export interface OpenQuestion {
  row: ImportRowView;
  question: ImportQuestion;
}

/** Every unanswered question on rows still waiting, in file order. */
export function openQuestions(rows: ImportRowView[]): OpenQuestion[] {
  return rows
    .filter((row) => row.status === 'proposed')
    .flatMap((row) => row.questions.filter((question) => question.answer === null).map((question) => ({ row, question })));
}

export default function QuestionStepper({
  questions,
  busy,
  onAnswer,
}: {
  questions: OpenQuestion[];
  busy: boolean;
  onAnswer: (row: ImportRowView, question: ImportQuestion, value: string) => void;
}) {
  const [index, setIndex] = useState(0);

  if (questions.length === 0) return null;

  const at = Math.min(index, questions.length - 1);
  const { row, question } = questions[at];

  return (
    <section aria-label="Questions" className="tile tone-warn px-4 py-3.5">
      <div className="flex items-center gap-2">
        <HelpCircle size={15} className="flex-none text-warning" aria-hidden="true" />
        <p className="text-[12px] font-medium tracking-wide text-secondary uppercase">
          Question {at + 1} of {questions.length}
        </p>

        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={() => setIndex(Math.max(at - 1, 0))}
            disabled={at === 0}
            aria-label="Previous question"
            className="icon-pill h-7 w-7 disabled:opacity-35"
          >
            <ChevronLeft size={14} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setIndex(Math.min(at + 1, questions.length - 1))}
            disabled={at === questions.length - 1}
            aria-label="Next question"
            className="icon-pill h-7 w-7 disabled:opacity-35"
          >
            <ChevronRight size={14} aria-hidden="true" />
          </button>
        </div>
      </div>

      <p className="mt-2 text-[12px] text-muted">
        Row {row.row_number} · {rowTitle(row)}
        {row.source.sheet ? ` · ${row.source.sheet}` : ''}
      </p>
      <p className="mt-1 text-[14px] leading-[1.45] text-primary">{question.text}</p>

      <ul className="mt-3 space-y-1.5">
        {question.options.map((choice) => (
          <li key={choice.value}>
            <button
              type="button"
              disabled={busy}
              onClick={() => onAnswer(row, question, choice.value)}
              className="flex w-full items-center gap-2 rounded-lg border border-line bg-panel px-3 py-2 text-left text-[13px] text-primary transition hover:border-accent disabled:opacity-50"
            >
              {busy && <Loader2 size={13} className="flex-none animate-spin text-muted" aria-hidden="true" />}
              <span className="min-w-0 flex-1">{choice.label}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

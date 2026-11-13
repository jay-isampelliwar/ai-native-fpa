'use client';

import { Loader2, Search } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';

import { documents } from '@/lib/api';
import type { InstrumentChoice } from '@/lib/types';

/**
 * A name box that suggests stocks and funds as you type, from two letters on.
 *
 * Each keystroke cancels the search before it, so a slow answer for "pa" never overwrites the
 * list for "parag". Arrow keys move through the list, Enter picks, Escape closes it.
 */

const WAIT_MS = 250;
const MIN_CHARS = 2;

export default function InstrumentSearch({
  initial,
  onPick,
}: {
  initial: string;
  onPick: (choice: InstrumentChoice) => void;
}) {
  const [text, setText] = useState(initial);
  const [choices, setChoices] = useState<InstrumentChoice[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const typed = useRef(false);
  const listId = useId();

  useEffect(() => {
    if (!typed.current || text.trim().length < MIN_CHARS) {
      setChoices([]);
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);

      documents
        .searchInstruments(text.trim(), controller.signal)
        .then((found) => {
          setChoices(found);
          setActive(0);
          setOpen(true);
        })
        .catch(() => {
          if (!controller.signal.aborted) setChoices([]);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, WAIT_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [text]);

  function pick(choice: InstrumentChoice) {
    typed.current = false;
    setText(choice.name);
    setOpen(false);
    onPick(choice);
  }

  return (
    <div className="relative">
      <Search size={14} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted" aria-hidden="true" />

      <input
        value={text}
        onChange={(event) => {
          typed.current = true;
          setText(event.target.value);
        }}
        onFocus={() => choices.length > 0 && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={(event) => {
          if (!open || choices.length === 0) return;

          if (event.key === 'ArrowDown') {
            event.preventDefault();
            setActive((index) => Math.min(index + 1, choices.length - 1));
          } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            setActive((index) => Math.max(index - 1, 0));
          } else if (event.key === 'Enter') {
            event.preventDefault();
            pick(choices[active]);
          } else if (event.key === 'Escape') {
            setOpen(false);
          }
        }}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        placeholder="Type a fund or stock name"
        className="w-full rounded-lg border border-line bg-panel py-2 pr-8 pl-8 text-[13px] text-primary placeholder:text-muted focus:border-accent focus:outline-none"
      />

      {loading && <Loader2 size={14} className="absolute top-1/2 right-3 -translate-y-1/2 animate-spin text-muted" aria-hidden="true" />}

      {open && (
        <ul
          id={listId}
          role="listbox"
          className="quiet-scroll absolute inset-x-0 top-full z-20 mt-1 max-h-64 overflow-y-auto rounded-lg border border-line bg-panel-elevated py-1 shadow-[var(--shadow-card)]"
        >
          {choices.length === 0 ? (
            <li className="px-3 py-2 text-[12.5px] text-muted">No stock or fund matches</li>
          ) : (
            choices.map((choice, index) => (
              <li
                key={choice.value}
                role="option"
                aria-selected={index === active}
                onMouseDown={(event) => {
                  event.preventDefault();
                  pick(choice);
                }}
                onMouseEnter={() => setActive(index)}
                className={`cursor-pointer px-3 py-2 text-[12.5px] ${index === active ? 'bg-accent-soft text-primary' : 'text-secondary'}`}
              >
                <span className="block truncate text-primary">{choice.name}</span>
                <span className="block text-[11.5px] text-muted">
                  {choice.kind === 'fund' ? 'Fund' : 'Stock'} · {choice.isin}
                </span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

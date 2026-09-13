'use client';

import { Calendar, Check, ChevronDown } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

/**
 * The period control, built as a real listbox rather than a styled `<select>`.
 *
 * A native select cannot carry the check mark and spacing the reference shows, and
 * a div with a click handler cannot be operated from a keyboard. This is the
 * middle path: a button that owns `aria-expanded`, a `listbox` of `option`s, and
 * arrow keys, Home, End, Enter and Escape wired to do what they do in a native
 * one. The doc asks specifically for keyboard-operable date selectors.
 *
 * Closing on outside click uses `pointerdown` rather than `click` so that pressing
 * on the page dismisses the menu at the moment of the press, the way every other
 * menu on the platform behaves.
 */

export interface MonthOption {
  id: string;
  label: string;
}

export default function MonthSelect({
  options,
  value,
  onChange,
  compact = false,
}: {
  options: MonthOption[];
  value: string;
  onChange: (id: string) => void;
  /** The smaller form used inside the income and expense cards. */
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(() => Math.max(0, options.findIndex((o) => o.id === value)));

  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);

  const selected = options.find((option) => option.id === value);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }

    document.addEventListener('pointerdown', onPointerDown);

    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [open]);

  // Moving focus is a DOM instruction, not state, so it stays in an effect. Where
  // the cursor should land is decided in `open()` instead: an effect that reacts to
  // the menu opening by setting state renders the list once in the wrong place and
  // then again in the right one.
  useEffect(() => {
    if (open) list.current?.focus();
  }, [open]);

  function commit(index: number) {
    const option = options[index];

    if (option) onChange(option.id);

    setOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Escape') {
      setOpen(false);
      return;
    }

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((current) => {
        const next = event.key === 'ArrowDown' ? current + 1 : current - 1;

        return Math.min(options.length - 1, Math.max(0, next));
      });
      return;
    }

    if (event.key === 'Home') {
      event.preventDefault();
      setActive(0);
      return;
    }

    if (event.key === 'End') {
      event.preventDefault();
      setActive(options.length - 1);
      return;
    }

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      commit(active);
    }
  }

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => {
          // Land on the selected month rather than wherever the pointer last hovered.
          if (!open) setActive(Math.max(0, options.findIndex((option) => option.id === value)));
          setOpen((current) => !current);
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Period: ${selected?.label ?? ''}. Change period`}
        className={`inline-flex items-center gap-1.5 rounded-full border border-line bg-panel-subtle font-medium text-primary transition hover:border-line-strong ${
          compact ? 'px-2.5 py-1.5 text-[12px]' : 'px-3 py-2 text-[13px]'
        }`}
      >
        {!compact && <Calendar size={14} className="text-secondary" aria-hidden="true" />}
        {selected?.label ?? 'Select'}
        <ChevronDown
          size={14}
          className={`text-secondary transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <ul
          ref={list}
          role="listbox"
          tabIndex={-1}
          aria-activedescendant={`month-${options[active]?.id}`}
          onKeyDown={onKeyDown}
          className="quiet-scroll absolute right-0 z-50 mt-1.5 max-h-64 w-52 overflow-y-auto rounded-xl border border-line bg-panel-elevated p-1 shadow-[var(--shadow-card)] outline-none"
        >
          {options.map((option, index) => {
            const isSelected = option.id === value;

            return (
              <li
                key={option.id}
                id={`month-${option.id}`}
                role="option"
                aria-selected={isSelected}
                onClick={() => commit(index)}
                onMouseEnter={() => setActive(index)}
                className={`flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] ${
                  index === active ? 'bg-panel-subtle text-primary' : 'text-secondary'
                }`}
              >
                <Check
                  size={14}
                  className={isSelected ? 'text-accent' : 'opacity-0'}
                  aria-hidden="true"
                />
                {option.label}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

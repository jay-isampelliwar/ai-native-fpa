'use client';

import { FileText, Plus } from 'lucide-react';

import { FORMS } from '@/lib/forms';
import type { EmptyBlock, FormKind } from '@/lib/types';

/** The name of the window event EmptyCard sends to open a blank form beside the chat. */
export const OPEN_FORM_EVENT = 'fpa:open-form';

export interface OpenFormDetail {
  form: FormKind;
}

/** "Add a loan", from the form's own title. */
function addLabel(form: FormKind): string {
  const title = FORMS[form].title.toLowerCase();

  return `Add ${/^[aeiou]/.test(title) ? 'an' : 'a'} ${title}`;
}

/** An `empty` block: nothing saved of this kind yet, with a button that opens the form when there is one. */
export default function EmptyCard({ block }: { block: EmptyBlock }) {
  return (
    <div className="px-1 py-2 text-center">
      <div className="mx-auto grid h-10 w-10 place-items-center rounded-xl bg-panel-subtle text-muted">
        <FileText aria-hidden className="h-4 w-4" strokeWidth={2} />
      </div>

      <p className="mt-3 text-[14.5px] font-semibold text-primary">{block.title}</p>
      {block.text && <p className="mt-0.5 text-[13px] text-muted">{block.text}</p>}

      {block.form && (
        <button
          type="button"
          onClick={() => window.dispatchEvent(new CustomEvent<OpenFormDetail>(OPEN_FORM_EVENT, { detail: { form: block.form! } }))}
          className="chip-button mx-auto mt-3 h-9 gap-1.5 px-3.5 text-[13px] font-medium"
        >
          <Plus aria-hidden className="h-3.5 w-3.5" strokeWidth={2.25} />
          {addLabel(block.form)}
        </button>
      )}
    </div>
  );
}

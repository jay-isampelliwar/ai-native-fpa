'use client';

import { AlertTriangle, CheckCircle2, ChevronRight, FileSpreadsheet, HelpCircle } from 'lucide-react';
import { useEffect, useState } from 'react';

import { documents } from '@/lib/api';
import type { DocumentView } from '@/lib/types';

/**
 * A short card for one attached file under the reply about it: what it holds and what it waits for.
 *
 * Nothing is approved here. The full review, with questions, edits and the Approve button, opens
 * in the panel beside the chat, so a long file never pushes the conversation off the screen.
 */

export default function ImportReview({
  documentId,
  onOpen,
}: {
  documentId: number;
  onOpen: (documentId: number) => void;
}) {
  const [document, setDocument] = useState<DocumentView | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let live = true;

    documents
      .get(documentId)
      .then((found) => live && setDocument(found))
      .catch((error: unknown) => live && setFailure(error instanceof Error ? error.message : 'This file could not be loaded'));

    return () => {
      live = false;
    };
  }, [documentId]);

  if (failure) return <p className="mt-2 text-[12px] text-negative">{failure}</p>;

  if (!document) return null;

  const checks = document.checks;
  const questions = checks.open_questions ?? 0;
  const errors = checks.with_errors ?? 0;

  return (
    <button
      type="button"
      onClick={() => onOpen(document.id)}
      className="tile mt-2 flex w-full items-center gap-3 px-3 py-2.5 text-left transition hover:bg-panel-elevated"
    >
      <span className="badge flex-none">
        <FileSpreadsheet size={16} aria-hidden="true" />
      </span>

      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-semibold text-primary">{document.original_filename}</span>
        <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[12px] text-secondary">
          {document.status === 'imported' ? (
            <span className="flex items-center gap-1 text-positive">
              <CheckCircle2 size={12} aria-hidden="true" /> Imported
            </span>
          ) : document.status === 'needs_mapping' ? (
            <span className="text-warning">Pick the columns to read it</span>
          ) : document.status === 'needs_password' ? (
            <span className="text-warning">Locked, needs its password</span>
          ) : document.status === 'needs_consent' ? (
            <span className="text-warning">Waiting for your OK to let the model read it</span>
          ) : document.status === 'failed' ? (
            <span className="text-negative">{document.error_message ?? 'Could not be read'}</span>
          ) : (
            <span>{checks.ready ?? 0} ready</span>
          )}

          {questions > 0 && (
            <span className="flex items-center gap-1 text-warning">
              <HelpCircle size={12} aria-hidden="true" /> {questions} to answer
            </span>
          )}

          {errors > 0 && (
            <span className="flex items-center gap-1 text-warning">
              <AlertTriangle size={12} aria-hidden="true" /> {errors} to fix
            </span>
          )}
        </span>
      </span>

      <span className="flex flex-none items-center gap-0.5 text-[12.5px] font-medium text-accent">
        Review <ChevronRight size={14} aria-hidden="true" />
      </span>
    </button>
  );
}

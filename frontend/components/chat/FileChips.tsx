'use client';

import { AlertTriangle, CheckCircle2, FileText, Loader2, Lock, X } from 'lucide-react';
import { useState } from 'react';

import type { Attachment } from '@/lib/useUploads';

/**
 * The attached files, drawn above the composer while they upload.
 *
 * Each chip says in words what its file needs, because the states ask different things of the
 * reader: one is still uploading, one is locked, one has pages only the model can read, one has
 * questions, one failed. A locked PDF takes its password right in the chip; the password is sent
 * once and never kept. Clicking a chip that reached the server opens its review beside the chat.
 */

function describe(item: Attachment): { label: string; tone: string } {
  switch (item.status) {
    case 'uploading':
      return { label: 'Uploading…', tone: 'text-muted' };
    case 'needs_mapping':
      return { label: 'Pick the columns to read it', tone: 'text-warning' };
    case 'needs_password':
      return { label: 'Locked, needs its password', tone: 'text-warning' };
    case 'needs_consent':
      return { label: `${item.modelPages} page${item.modelPages === 1 ? '' : 's'} for the model, open to allow`, tone: 'text-warning' };
    case 'parsed': {
      const rows = `${item.rowCount} row${item.rowCount === 1 ? '' : 's'}`;
      const questions = item.openQuestions ? `, ${item.openQuestions} to answer` : '';

      return { label: `${item.repeat ? 'Uploaded before · ' : ''}${rows}${questions}`, tone: item.openQuestions ? 'text-warning' : 'text-secondary' };
    }
    case 'imported':
      return { label: item.repeat ? 'Imported before' : 'Imported', tone: 'text-positive' };
    case 'rejected':
      return { label: 'Import undone', tone: 'text-muted' };
    default:
      return { label: 'Could not be read', tone: 'text-negative' };
  }
}

export default function FileChips({
  attachments,
  onRemove,
  onOpen,
  onUnlock,
}: {
  attachments: Attachment[];
  onRemove: (key: string) => void;
  onOpen: (documentId: number) => void;
  onUnlock: (key: string, documentId: number, password: string) => void;
}) {
  if (attachments.length === 0) return null;

  return (
    <ul className="mb-2 flex flex-col gap-1.5">
      {attachments.map((item) => (
        <Chip key={item.key} item={item} onRemove={onRemove} onOpen={onOpen} onUnlock={onUnlock} />
      ))}
    </ul>
  );
}

function Chip({
  item,
  onRemove,
  onOpen,
  onUnlock,
}: {
  item: Attachment;
  onRemove: (key: string) => void;
  onOpen: (documentId: number) => void;
  onUnlock: (key: string, documentId: number, password: string) => void;
}) {
  const [password, setPassword] = useState('');
  const { label, tone } = describe(item);

  function sendPassword() {
    if (!password || typeof item.documentId !== 'number') return;

    onUnlock(item.key, item.documentId, password);
    setPassword('');
  }

  const openable = typeof item.documentId === 'number';

  return (
    <li className="rounded-xl border border-line bg-panel-subtle px-2.5 py-2">
      <div className="flex items-center gap-2">
        <span className="flex-none text-muted" aria-hidden="true">
          {item.status === 'uploading' ? (
            <Loader2 size={14} className="animate-spin" />
          ) : item.status === 'failed' ? (
            <AlertTriangle size={14} />
          ) : item.status === 'needs_password' ? (
            <Lock size={14} />
          ) : item.status === 'imported' ? (
            <CheckCircle2 size={14} />
          ) : (
            <FileText size={14} />
          )}
        </span>

        <button
          type="button"
          disabled={!openable}
          onClick={() => openable && onOpen(item.documentId as number)}
          title={openable ? `Review ${item.name}` : item.name}
          className="min-w-0 flex-1 truncate text-left text-[12.5px] text-primary enabled:hover:underline disabled:cursor-default"
        >
          {item.name}
        </button>

        <span className={`flex-none text-[11.5px] ${tone}`}>{label}</span>

        <button
          type="button"
          onClick={() => onRemove(item.key)}
          aria-label={`Remove ${item.name} from this message`}
          className="grid h-6 w-6 flex-none place-items-center rounded-lg text-muted transition hover:text-primary"
        >
          <X size={13} aria-hidden="true" />
        </button>
      </div>

      {item.status === 'needs_password' && (
        <div className="mt-2 flex items-center gap-1.5 pl-6">
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== 'Enter') return;

              event.preventDefault();
              sendPassword();
            }}
            placeholder="PDF password"
            aria-label={`Password for ${item.name}`}
            autoComplete="off"
            className="min-w-0 flex-1 rounded-lg border border-line bg-panel px-2 py-1 text-[12px] text-primary outline-none placeholder:text-muted"
          />
          <button
            type="button"
            disabled={!password}
            onClick={sendPassword}
            className="send-gradient flex-none rounded-lg px-2.5 py-1 text-[12px] font-medium disabled:cursor-not-allowed disabled:opacity-40"
          >
            Open
          </button>
        </div>
      )}

      {item.error && (item.status === 'failed' || item.status === 'needs_password') && (
        <p className="mt-1.5 pl-6 text-[11.5px] leading-[1.45] text-secondary">{item.error}</p>
      )}
    </li>
  );
}

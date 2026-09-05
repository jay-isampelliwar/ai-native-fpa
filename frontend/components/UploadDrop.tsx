'use client';

import { useRef, useState } from 'react';

/**
 * Drop a statement into the app.
 *
 * Deliberately styled as a control rather than a hint. A dashed hairline with grey-on-cream text
 * reads as a caption, and a caption is not something anyone clicks. What makes it findable is the
 * icon chip carrying the accent colour, an opaque surface that lifts off the panel, and a label in
 * ink rather than muted grey.
 *
 * The accepted types are the ones something can actually read: spreadsheets and bank CSVs. Offering
 * PDF here would invite a file the extractor refuses, and a refusal after an upload is a worse
 * experience than a picker that never offered it.
 */
export default function UploadDrop({
  onFile,
  busy,
  progress,
}: {
  onFile: (file: File) => void;
  busy: boolean;
  progress: string | null;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  if (progress) {
    return (
      <div className="flex items-center gap-2.5 rounded-xl border border-[#00947a]/35 bg-[#00947a]/10 px-3.5 py-3">
        <Spinner />
        <span className="text-[12.5px] font-medium leading-4 text-[#0f5f50]">{progress}</span>
      </div>
    );
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        const file = event.dataTransfer.files?.[0];
        if (file && !busy) onFile(file);
      }}
    >
      <input
        ref={input}
        type="file"
        accept=".xlsx,.xlsm,.xls,.csv"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = ''; // so the same file can be picked twice
        }}
      />

      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={busy}
        className={`group flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
          over
            ? 'border-[#00947a] bg-[#00947a]/12 shadow-[0_0_0_3px_rgba(0,148,122,0.14)]'
            : 'border-[#00947a]/35 bg-white shadow-[0_1px_3px_rgba(16,59,54,0.06)] hover:border-[#00947a] hover:bg-[#00947a]/6'
        }`}
      >
        <span
          aria-hidden="true"
          className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#00947a]/12 text-[#00947a] transition group-hover:bg-[#00947a]/18"
        >
          <UploadIcon />
        </span>

        <span className="min-w-0 flex-1">
          <span className="block text-[13px] font-semibold leading-4 text-[#18312f]">
            {over ? 'Drop it here' : 'Upload a statement'}
          </span>
          <span className="block truncate text-[11.5px] leading-4 text-[#5d7470]">
            Holdings or bank exports — you review every row before it lands
          </span>
        </span>

        <span
          aria-hidden="true"
          className="shrink-0 text-[15px] leading-none text-[#00947a] transition group-hover:translate-x-0.5"
        >
          →
        </span>
      </button>
    </div>
  );
}

function UploadIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M8 10.5V2.5M8 2.5 5 5.5M8 2.5l3 3M2.5 10v2.5a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1V10"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Spinner() {
  return (
    <svg className="h-4 w-4 shrink-0 animate-spin text-[#00947a]" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" fill="none" />
      <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  );
}

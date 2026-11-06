'use client';

import { Newspaper } from 'lucide-react';
import { useState } from 'react';

import type { SourcesBlock } from '@/lib/types';

type Source = SourcesBlock['items'][number];

/** Show a page's date as "7 Nov 2026", or nothing when it is missing or not a date. */
function shortDate(value?: string | null): string | null {
  if (!value) return null;

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return null;

  return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** The page's own preview image, or a news icon when it has none or the site blocks it. */
function Picture({ image }: { image?: string | null }) {
  const [broken, setBroken] = useState(false);

  if (!image || broken) {
    return (
      <div className="grid aspect-video w-full place-items-center bg-[var(--panel-subtle)] text-muted">
        <Newspaper aria-hidden className="h-4 w-4" strokeWidth={1.75} />
      </div>
    );
  }

  return (
    // A plain img: these are outside news images, so no Next image domains to list and nothing passes through our server.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={image}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setBroken(true)}
      className="aspect-video w-full object-cover"
    />
  );
}

/** One page as a tile: its image on top, then its title, site and date. */
function Tile({ item }: { item: Source }) {
  const date = shortDate(item.published);

  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className="group block w-[152px] shrink-0 snap-start overflow-hidden rounded-lg border border-line bg-panel transition-colors hover:border-[var(--border-strong)]"
    >
      <Picture image={item.image} />

      <div className="px-2 pb-2 pt-1.5">
        <span className="line-clamp-2 text-[12px] font-medium leading-snug text-primary group-hover:underline">
          {item.title}
        </span>
        <span className="mt-0.5 block truncate text-[11px] text-muted">{date ? `${item.site} · ${date}` : item.site}</span>
      </div>
    </a>
  );
}

/** A `sources` block: the web pages a search used, as a row of small image tiles straight in the reply, scrolling sideways for more. */
export default function SourcesCard({ block }: { block: SourcesBlock }) {
  return (
    <div>
      <p className="text-[12px] font-medium text-muted">{block.title}</p>

      <div className="-mb-1 mt-2 flex snap-x snap-mandatory gap-2 overflow-x-auto overscroll-x-contain pb-2 [scrollbar-width:thin]">
        {block.items.map((item) => (
          <Tile key={item.url} item={item} />
        ))}
      </div>
    </div>
  );
}

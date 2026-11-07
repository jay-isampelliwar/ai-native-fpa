'use client';

import { Newspaper } from 'lucide-react';
import { useState } from 'react';

import type { SourcesBlock } from '@/lib/types';

type Source = SourcesBlock['items'][number];

/** Show a page's date as "7 Nov", or nothing when it is missing or not a date. */
function shortDate(value?: string | null): string | null {
  if (!value) return null;

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return null;

  return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

/** The page's own preview image filling the tile, or a news icon when it has none or the site blocks it. */
function Picture({ image }: { image?: string | null }) {
  const [broken, setBroken] = useState(false);

  if (!image || broken) {
    return (
      <div className="absolute inset-0 grid place-items-center bg-[var(--panel-subtle)] text-muted">
        <Newspaper aria-hidden className="h-[18px] w-[18px]" strokeWidth={1.75} />
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
      className="absolute inset-0 h-full w-full object-cover"
    />
  );
}

/** One page as a tile: its image behind, the title and site over a dark fade at the bottom. */
function Tile({ item }: { item: Source }) {
  const date = shortDate(item.published);

  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className="group relative block h-[112px] w-[168px] shrink-0 snap-start overflow-hidden rounded-xl border border-line bg-panel-subtle transition-colors hover:border-[var(--border-strong)]"
    >
      <Picture image={item.image} />
      <div aria-hidden className="absolute inset-0 bg-[linear-gradient(180deg,transparent_30%,rgba(8,9,10,0.88)_100%)]" />

      <div className="absolute inset-x-2.5 bottom-2 text-[#f4f5f6]">
        <span className="line-clamp-2 text-[12px] font-semibold leading-[1.3] group-hover:underline">{item.title}</span>
        <span className="mt-0.5 block truncate text-[10.5px] opacity-75">{date ? `${item.site} · ${date}` : item.site}</span>
      </div>
    </a>
  );
}

/** A `sources` block: the web pages a search used, as a row of image tiles straight in the reply, scrolling sideways for more. */
export default function SourcesCard({ block }: { block: SourcesBlock }) {
  return (
    <div>
      <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-muted">{block.title}</p>

      <div className="-mb-1 mt-2 flex snap-x snap-mandatory gap-2 overflow-x-auto overscroll-x-contain pb-2 [scrollbar-width:thin]">
        {block.items.map((item) => (
          <Tile key={item.url} item={item} />
        ))}
      </div>
    </div>
  );
}

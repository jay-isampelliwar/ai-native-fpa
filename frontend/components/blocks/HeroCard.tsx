'use client';

import { Wallet } from 'lucide-react';

import type { HeroBlock } from '@/lib/types';
import { BigNumber, Delta, FactTiles, TileHead } from '@/components/blocks/Tile';

/** A `hero` block: one big number that answers the question, its change, and a few facts under it. */
export default function HeroCard({ block }: { block: HeroBlock }) {
  return (
    <div>
      <TileHead title={block.title} subtitle={block.as_of} icon={Wallet} />

      <BigNumber>{block.value}</BigNumber>

      {block.change && <Delta change={block.change} note={block.change_note} />}

      {block.facts && block.facts.length > 0 && <FactTiles facts={block.facts} columns={block.facts.length >= 4 ? 4 : block.facts.length === 3 ? 3 : 2} />}
    </div>
  );
}

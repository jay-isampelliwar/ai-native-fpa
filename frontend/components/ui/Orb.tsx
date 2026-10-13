import ThinkingOrb from '@/components/ui/ThinkingOrb';

/**
 * The assistant's mark: the `working` thinking orb, particles on tilted orbits.
 *
 * `working` is used for the mark because no moment in the chat uses it, so the brand never
 * looks like a status. `still` draws one frame and stops.
 */
export default function Orb({
  size = 28,
  className = '',
  still = false,
}: {
  size?: number;
  className?: string;
  still?: boolean;
}) {
  return <ThinkingOrb state="working" size={size} still={still} label="" className={className} />;
}

/**
 * The assistant's mark: glowing rings turning around a dark core.
 *
 * All drawing is in `.orb` in globals.css. This only sets the size and how thick the
 * ring is, because a 28px avatar needs a thicker ring than an 80px hero to read as one.
 */
export default function Orb({ size = 28, className = '' }: { size?: number; className?: string }) {
  const ring = Math.max(2, Math.round(size * 0.09));

  return (
    <span
      aria-hidden="true"
      className={`orb ${className}`}
      style={
        {
          width: size,
          height: size,
          '--orb-size': `${size}px`,
          '--orb-ring': `${ring}px`,
        } as React.CSSProperties
      }
    />
  );
}

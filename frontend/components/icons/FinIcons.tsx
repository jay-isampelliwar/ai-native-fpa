import type { CSSProperties, ReactNode } from 'react';

/**
 * Mosaic's own icons, drawn for what this app does: records, approvals, goals, statements.
 *
 * Every icon is duotone on a 24px grid: a 1.75px line in the current text colour, and one part
 * filled with the same colour at low strength (`fi-fill`). Each has one detail (`fi-move`) that
 * shifts when the control holding it is hovered or focused — a pencil writes, a bin lid lifts,
 * a statement rises. Nothing loops and nothing moves on its own.
 *
 * The hover rules live in `globals.css` under "Icons", keyed on any button, link or `.fi-host`
 * around the icon, so a parent control drives it without passing state down. Under reduced motion
 * the global rule makes the shift instant.
 *
 * Generic controls (copy, close, chevrons) stay on lucide; these are only for the app's own ideas.
 */

interface IconProps {
  size?: number;
  className?: string;
  /** A name for a reader when the icon stands alone; leave out when text sits beside it. */
  title?: string;
}

function Icon({ size = 18, className = '', title, children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`fin-icon ${className}`}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {children}
    </svg>
  );
}

/** The part that shifts on hover, with how it shifts. */
function Move({ to, origin, children }: { to: string; origin?: string; children: ReactNode }) {
  return (
    <g className="fi-move" style={{ '--fi-move': to, transformOrigin: origin } as CSSProperties}>
      {children}
    </g>
  );
}

/** Change a saved record: a ledger card, and a pencil that writes when pointed at. */
export function EditRecord(props: IconProps) {
  return (
    <Icon {...props}>
      <rect className="fi-fill" x="3" y="4" width="13" height="16" rx="2" />
      <path d="M6.5 9h6M6.5 12.5h4" />
      <Move to="translate(-1.2px, 1.2px)">
        <path d="M18.6 8.4l2 2-7.4 7.4-2.9.9.9-2.9z" />
      </Move>
    </Icon>
  );
}

/** Remove a saved record: a bin whose lid lifts on hover. */
export function RemoveRecord(props: IconProps) {
  return (
    <Icon {...props}>
      <path className="fi-fill" d="M6 8.5h12l-1 10.8a2 2 0 0 1-2 1.7H9a2 2 0 0 1-2-1.7z" />
      <path d="M10 12v5M14 12v5" />
      <Move to="translate(0.6px, -1.6px) rotate(9deg)" origin="right bottom">
        <path d="M4.5 8.5h15M9.5 8.5V6.5A1.5 1.5 0 0 1 11 5h2a1.5 1.5 0 0 1 1.5 1.5v2" />
      </Move>
    </Icon>
  );
}

/** Check worked-out units: two rupee coins; the front one grows a little on hover. */
export function CheckSum(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M8.6 8.6A6 6 0 1 1 15.4 15.4" />
      <Move to="scale(1.1)">
        <circle className="fi-fill" cx="9.5" cy="14.5" r="6" />
        <path d="M7.4 12h4.2M7.4 14h4.2M8.4 12c2.4 0 2.4 3.6 0 3.6l2.8 2.6" />
      </Move>
    </Icon>
  );
}

/** A guarded action that needs a yes: a shield whose tick grows on hover. */
export function Guard(props: IconProps) {
  return (
    <Icon {...props}>
      <path className="fi-fill" d="M12 3l7 2.8v5.4c0 4.4-3 7.9-7 9.8-4-1.9-7-5.4-7-9.8V5.8z" />
      <Move to="scale(1.15)">
        <path d="M9 12.2l2 2 4-4.2" />
      </Move>
    </Icon>
  );
}

/** A form to fill: a sheet of fields, and a pen that moves to write. */
export function FormSheet(props: IconProps) {
  return (
    <Icon {...props}>
      <rect className="fi-fill" x="3.5" y="3" width="13" height="18" rx="2" />
      <path d="M7 8h6M7 11.5h6M7 15h3" />
      <Move to="translate(-1.4px, 0.6px)">
        <path d="M19.4 12.3l1.6 1.6-5.6 5.6-2.3.6.6-2.3z" />
      </Move>
    </Icon>
  );
}

/** Details already sent: a sheet with a check seal that grows on hover. */
export function DetailsShared(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M13 19H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v6" />
      <path d="M7.5 7.5h5M7.5 11h3" />
      <Move to="scale(1.12)">
        <circle className="fi-fill" cx="17" cy="17" r="4.5" />
        <path d="M15.2 17.1l1.3 1.3 2.4-2.6" />
      </Move>
    </Icon>
  );
}

/** Attach a bank or holdings statement: a page with a folded corner that rises on hover. */
export function Statement(props: IconProps) {
  return (
    <Icon {...props}>
      <Move to="translateY(-1.6px)">
        <path className="fi-fill" d="M7 3h7l4.5 4.5V19a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />
        <path d="M14 3v4.5h4.5M8.5 12h6.5M8.5 15.5h4" />
      </Move>
    </Icon>
  );
}

/** Send: a paper plane that nudges forward on hover. */
export function SendPlane(props: IconProps) {
  return (
    <Icon {...props}>
      <Move to="translate(1.4px, -1.4px)">
        <path className="fi-fill" d="M21 3l-6.4 18-3.6-7.4L3.6 10z" />
        <path d="M21 3L11 13.6" />
      </Move>
    </Icon>
  );
}

/** On track, or a step that finished: a tinted disc with a tick. */
export function StatusOk(props: IconProps) {
  return (
    <Icon {...props}>
      <circle className="fi-fill" cx="12" cy="12" r="9" />
      <Move to="scale(1.12)">
        <path d="M8.5 12.2l2.4 2.4 4.6-4.8" />
      </Move>
    </Icon>
  );
}

/** Not on track, or a warning: a tinted triangle with a mark. */
export function StatusAlert(props: IconProps) {
  return (
    <Icon {...props}>
      <path className="fi-fill" d="M10.3 3.9L2.6 17.5a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
      <Move to="translateY(-0.8px)">
        <path d="M12 9v4.2M12 16.6h.01" />
      </Move>
    </Icon>
  );
}

/** A step that failed. */
export function StepError(props: IconProps) {
  return (
    <Icon {...props}>
      <circle className="fi-fill" cx="12" cy="12" r="9" />
      <path d="M9.2 9.2l5.6 5.6M14.8 9.2l-5.6 5.6" />
    </Icon>
  );
}

/** A step stopped by the person. */
export function StepStopped(props: IconProps) {
  return (
    <Icon {...props}>
      <circle className="fi-fill" cx="12" cy="12" r="9" />
      <rect x="9.5" y="9.5" width="5" height="5" rx="1" />
    </Icon>
  );
}

/** A step the person said no to on an approval card. */
export function StepRejected(props: IconProps) {
  return (
    <Icon {...props}>
      <circle className="fi-fill" cx="12" cy="12" r="9" />
      <path d="M8 16L16 8" />
    </Icon>
  );
}

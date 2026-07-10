import type { SVGProps } from 'react';

/**
 * Product-specific glyphs, drawn for Maestro. lucide-react still supplies the
 * secondary icons; these five carry meaning lucide has no word for.
 *
 * All inherit `currentColor` and default to 16px. Decorative by default —
 * when an icon is the sole content of a control, label the control, not the
 * icon.
 */
type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 16, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

/**
 * The brand mark: a conductor's baton. Maestro conducts three engines, so the
 * glyph is the act of conducting — the pivot of the hand, the raised baton,
 * and two gesture arcs trailing off as the beat lands.
 */
export function BatonIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="6.6" cy="17.4" r="2.4" fill="currentColor" />
      <path d="M8.5 15.5 18.4 5.6" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" />
      <circle cx="19.6" cy="4.4" r="1.5" fill="currentColor" />
      <path
        d="M11.2 20.6a8.2 8.2 0 0 0 6.4-4.2"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        opacity=".62"
      />
      <path
        d="M14.6 22.4a12 12 0 0 0 7.2-6.6"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        opacity=".3"
      />
    </Svg>
  );
}

/** Send: a paper plane. It says "this message flies off" better than an arrow. */
export function SendIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        d="M21.2 3.1 2.9 10.4a.6.6 0 0 0 .05 1.13l4.9 1.72 1.72 4.9a.6.6 0 0 0 1.13.05z"
        fill="currentColor"
      />
    </Svg>
  );
}

/** Skill: a hex chip with pins. A skill is a pluggable capability, not a magic wand. */
export function SkillIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        d="M12 2.9 19.4 7v9L12 20.1 4.6 16V7z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M12 8.2 15.6 10.3v4.2L12 16.6 8.4 14.5v-4.2z" fill="currentColor" opacity=".9" />
      <path
        d="M12 2.9v2.2M4.6 16l1.9-1.1M19.4 16l-1.9-1.1"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </Svg>
  );
}

/** AUTO authorization: safe to execute without asking. */
export function BoltIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M13.2 2.5 4.4 13.6h5.6l-.8 7.9 8.8-11.1h-5.6z" fill="currentColor" />
    </Svg>
  );
}

/** CONFIRM authorization: writes to MES, a human owns the decision. */
export function ShieldIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        d="M12 2.8 4.8 5.9v5.4c0 4.4 3 8.5 7.2 9.9 4.2-1.4 7.2-5.5 7.2-9.9V5.9z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="M8.8 12.1 11 14.3l4.2-4.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

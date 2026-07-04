/**
 * ProgressBar — shared 4px pill meter (capacity bars, kitting progress,
 * upload progress, confidence meters). The fill color is passed as a token
 * utility so each surface keeps its semantic hue.
 */
interface ProgressBarProps {
  /** 0–100; clamped. */
  percent: number;
  /** Token utility for the fill, e.g. 'bg-planning', 'bg-query'. */
  fillClassName?: string;
  /** Extra classes on the track (e.g. width/flex sizing). */
  className?: string;
}

export function ProgressBar({
  percent,
  fillClassName = 'bg-accent',
  className = '',
}: ProgressBarProps) {
  const width = `${Math.min(100, Math.max(0, percent))}%`;
  return (
    <div className={`h-2 overflow-hidden rounded-pill bg-surface-inset ${className}`}>
      <div
        className={`h-full rounded-pill transition-[width] duration-normal ease-out ${fillClassName}`}
        style={{ width }}
      />
    </div>
  );
}

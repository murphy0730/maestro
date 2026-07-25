export function BrandMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <polygon points="12,2.8 20,7.4 20,16.6 12,21.2 4,16.6 4,7.4" stroke="var(--accent)" strokeWidth="1.7" strokeLinejoin="round" />
      <polyline points="7.6,15.4 10.8,11.8 13.6,13.4 16.6,8.8" stroke="var(--text-primary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity=".86" />
      <circle cx="16.6" cy="8.8" r="1.7" fill="var(--accent)" />
    </svg>
  );
}

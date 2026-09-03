import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Base({ children, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      width={18}
      height={18}
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export function IconGrid(props: IconProps) {
  return (
    <Base {...props}>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.3" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.3" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.3" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.3" />
    </Base>
  );
}

export function IconSliders(props: IconProps) {
  return (
    <Base {...props}>
      <line x1="4" y1="6" x2="20" y2="6" />
      <circle cx="9" cy="6" r="2.2" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <circle cx="16" cy="12" r="2.2" />
      <line x1="4" y1="18" x2="20" y2="18" />
      <circle cx="11" cy="18" r="2.2" />
    </Base>
  );
}

export function IconRadar(props: IconProps) {
  return (
    <Base {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.5" opacity={0.6} />
      <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
      <line x1="12" y1="12" x2="18" y2="6.5" />
    </Base>
  );
}

export function IconArchive(props: IconProps) {
  return (
    <Base {...props}>
      <rect x="3.5" y="4" width="17" height="4.2" rx="1" />
      <path d="M4.5 8.2v9.3a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5V8.2" />
      <line x1="10" y1="12" x2="14" y2="12" />
    </Base>
  );
}

export function IconShip(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M4 14.5 6 20h12l2-5.5-8-2.5-8 2.5Z" />
      <line x1="12" y1="12" x2="12" y2="4" />
      <path d="M12 4 17 8.2H12" />
    </Base>
  );
}

export function IconPulse(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M3 12h4l2 6 4-14 2 8h6" />
    </Base>
  );
}

export function IconBolt(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M13 3 5 13.5h5.5L11 21l8-11h-5.5L13 3Z" />
    </Base>
  );
}

export function IconCheck(props: IconProps) {
  return (
    <Base {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M8.2 12.3 10.8 15l5-6" />
    </Base>
  );
}

export function IconCloud(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M7 18h10.5a3.5 3.5 0 0 0 .4-6.98A5.5 5.5 0 0 0 7.2 9.1 4 4 0 0 0 7 18Z" />
    </Base>
  );
}

export function IconDatabase(props: IconProps) {
  return (
    <Base {...props}>
      <ellipse cx="12" cy="5.5" rx="7.5" ry="2.7" />
      <path d="M4.5 5.5V12c0 1.5 3.4 2.7 7.5 2.7s7.5-1.2 7.5-2.7V5.5" />
      <path d="M4.5 12v6.5c0 1.5 3.4 2.7 7.5 2.7s7.5-1.2 7.5-2.7V12" />
    </Base>
  );
}

export function IconWaves(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M3 9c1.6-1.6 3.4-1.6 5 0s3.4 1.6 5 0 3.4-1.6 5 0" />
      <path d="M3 15c1.6-1.6 3.4-1.6 5 0s3.4 1.6 5 0 3.4-1.6 5 0" />
    </Base>
  );
}

export function IconSignal(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M4 18h.01M8.5 18v-3M13 18v-6M17.5 18V7" />
    </Base>
  );
}

export function IconDocument(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M7 3.5h7L18.5 8v12.5a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z" />
      <path d="M14 3.5V8h4.5" />
      <line x1="9" y1="12.5" x2="15" y2="12.5" />
      <line x1="9" y1="16" x2="15" y2="16" />
    </Base>
  );
}

export function IconAlertTriangle(props: IconProps) {
  return (
    <Base {...props}>
      <path d="M12 4 21 19H3L12 4Z" />
      <line x1="12" y1="10" x2="12" y2="14" />
      <circle cx="12" cy="17" r="0.6" fill="currentColor" stroke="none" />
    </Base>
  );
}

export const NAV_ICONS = {
  overview: IconGrid,
  analysis: IconSliders,
  investigation: IconRadar,
  incidents: IconArchive,
  vessels: IconShip,
  status: IconPulse
} as const;

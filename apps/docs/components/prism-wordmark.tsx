export function PrismWordmark() {
  return (
    <span className="inline-flex items-center gap-2 font-semibold tracking-tight text-fg">
      <PrismMark />
      <span>Prism</span>
      <span className="rounded-full border border-border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.18em] text-fg-subtle">
        Docs
      </span>
    </span>
  );
}

function PrismMark() {
  return (
    <svg
      aria-hidden="true"
      className="h-5 w-5 shrink-0"
      fill="none"
      viewBox="0 0 20 20"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M4 17L10 3L16 17H4Z"
        fill="url(#docs-prism-fill)"
        fillOpacity="0.16"
        stroke="url(#docs-prism-gradient)"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path d="M10 3V17" stroke="var(--color-border-strong)" strokeOpacity="0.7" />
      <defs>
        <linearGradient
          gradientUnits="userSpaceOnUse"
          id="docs-prism-gradient"
          x1="3"
          x2="17"
          y1="3"
          y2="17"
        >
          <stop stopColor="var(--color-trader)" />
          <stop offset="0.58" stopColor="var(--color-sentinel)" />
          <stop offset="1" stopColor="var(--color-verdict-good)" />
        </linearGradient>
        <radialGradient cx="0" cy="0" gradientTransform="translate(10 10) rotate(90) scale(9)" gradientUnits="userSpaceOnUse" id="docs-prism-fill" r="1">
          <stop stopColor="var(--color-trader)" />
          <stop offset="0.52" stopColor="var(--color-sentinel)" />
          <stop offset="1" stopColor="var(--color-verdict-good)" />
        </radialGradient>
      </defs>
    </svg>
  );
}

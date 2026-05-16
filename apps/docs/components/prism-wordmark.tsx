export function PrismWordmark() {
  return (
    <span className="inline-flex items-center gap-2 font-semibold tracking-tight text-fg">
      <span className="relative h-5 w-5 overflow-hidden rounded-md border border-border bg-canvas-raised prism-spectrum-border" />
      <span>Prism</span>
      <span className="rounded-full border border-border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.18em] text-fg-subtle">
        Docs
      </span>
    </span>
  );
}

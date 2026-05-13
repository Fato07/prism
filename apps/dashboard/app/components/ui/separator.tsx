/**
 * Separator — a subtle dividing line.
 *
 * Defaults to a horizontal hairline using the theme border tokens; renders
 * vertically when `orientation="vertical"` is set.
 */

import { cn } from "@/lib/utils";

interface SeparatorProps {
  orientation?: "horizontal" | "vertical";
  className?: string;
}

export function Separator({
  orientation = "horizontal",
  className,
}: SeparatorProps) {
  return (
    <span
      role="separator"
      aria-orientation={orientation}
      className={cn(
        "block bg-[var(--color-border)]",
        orientation === "horizontal" ? "h-px w-full" : "h-full w-px",
        className,
      )}
    />
  );
}

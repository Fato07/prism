/**
 * Skeleton — animated placeholder for content loading from Neon/IPFS.
 *
 * Uses CSS shimmer rather than JS, so it's safe in server components.
 */

import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <span
      className={cn(
        "inline-block rounded-md bg-[var(--color-canvas-raised)]",
        "animate-pulse",
        className,
      )}
      aria-hidden="true"
    />
  );
}

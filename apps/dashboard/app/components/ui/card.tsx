import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("rounded-lg border border-gray-800 bg-gray-900/50 shadow-sm", className)}>
      {children}
    </div>
  );
}

export function CardHeader({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("flex flex-col space-y-1.5 p-4 pb-2", className)}>
      {children}
    </div>
  );
}

export function CardTitle({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <h3 className={cn("text-lg font-semibold leading-none tracking-tight", className)}>
      {children}
    </h3>
  );
}

export function CardContent({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("p-4 pt-0", className)}>
      {children}
    </div>
  );
}

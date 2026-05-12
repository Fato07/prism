import { cn } from "@/lib/utils";

const variantStyles: Record<string, string> = {
  default: "bg-gray-700 text-gray-100",
  reject: "bg-red-900/50 text-red-300 border-red-700",
  warn: "bg-amber-900/50 text-amber-300 border-amber-700",
  pass: "bg-green-900/50 text-green-300 border-green-700",
  endorse: "bg-emerald-900/50 text-emerald-300 border-emerald-700",
  outline: "border border-gray-600 text-gray-300",
  buy: "bg-blue-900/50 text-blue-300 border-blue-700",
  sell: "bg-red-900/50 text-red-300 border-red-700",
};

export function Badge({
  className,
  variant = "default",
  children,
}: {
  className?: string;
  variant?: keyof typeof variantStyles;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium border",
        variantStyles[variant] ?? variantStyles.default,
        className,
      )}
    >
      {children}
    </span>
  );
}

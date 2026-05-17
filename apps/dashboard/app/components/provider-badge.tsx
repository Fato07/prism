import { cn } from "@/lib/utils";
import type { ConnectorPassport } from "@/lib/connectors";

export type ProviderBrandId =
  | "exa"
  | "firecrawl"
  | "tavily"
  | "brave"
  | "parallel"
  | "webhook"
  | "custom_mcp";

export interface ProviderBrand {
  id: ProviderBrandId;
  name: string;
  shortName: string;
  logoSrc: string;
  accentClass: string;
}

const PROVIDER_BRANDS: Record<ProviderBrandId, ProviderBrand> = {
  exa: {
    id: "exa",
    name: "Exa",
    shortName: "Exa",
    logoSrc: "/provider-logos/exa.svg",
    accentClass: "from-[#1F40ED]/25 to-[var(--color-sentinel)]/10",
  },
  firecrawl: {
    id: "firecrawl",
    name: "Firecrawl",
    shortName: "Firecrawl",
    logoSrc: "/provider-logos/firecrawl.svg",
    accentClass: "from-orange-500/25 to-red-500/10",
  },
  tavily: {
    id: "tavily",
    name: "Tavily",
    shortName: "Tavily",
    logoSrc: "/provider-logos/tavily.svg",
    accentClass: "from-emerald-400/25 to-cyan-400/10",
  },
  brave: {
    id: "brave",
    name: "Brave Search",
    shortName: "Brave",
    logoSrc: "/provider-logos/brave.svg",
    accentClass: "from-orange-500/25 to-amber-400/10",
  },
  parallel: {
    id: "parallel",
    name: "Parallel",
    shortName: "Parallel",
    logoSrc: "/provider-logos/parallel.svg",
    accentClass: "from-zinc-200/15 to-zinc-500/10",
  },
  webhook: {
    id: "webhook",
    name: "Webhook bridge",
    shortName: "Webhook",
    logoSrc: "/provider-logos/webhook.svg",
    accentClass: "from-[var(--color-sentinel)]/25 to-[var(--color-trader)]/10",
  },
  custom_mcp: {
    id: "custom_mcp",
    name: "Custom MCP",
    shortName: "MCP",
    logoSrc: "/provider-logos/custom-mcp.svg",
    accentClass: "from-[var(--color-trader)]/20 to-[var(--color-sentinel)]/10",
  },
};

export function providerBrandFromText(value: string | null | undefined): ProviderBrand | null {
  const haystack = (value ?? "").toLowerCase();
  if (!haystack) return null;
  const tokens = new Set(haystack.match(/[a-z0-9]+/g) ?? []);
  const containsToken = (...values: string[]) => values.some((token) => tokens.has(token));

  if (containsToken("firecrawl")) return PROVIDER_BRANDS.firecrawl;
  if (containsToken("tavily")) return PROVIDER_BRANDS.tavily;
  if (containsToken("brave")) return PROVIDER_BRANDS.brave;
  if (containsToken("parallel")) return PROVIDER_BRANDS.parallel;
  if (containsToken("exa")) return PROVIDER_BRANDS.exa;
  if (containsToken("webhook") || haystack.includes("custom_webhook")) return PROVIDER_BRANDS.webhook;
  if (containsToken("mcp")) return PROVIDER_BRANDS.custom_mcp;
  return null;
}

export function connectorProviderBrand(connector: ConnectorPassport | null | undefined): ProviderBrand {
  if (!connector) return PROVIDER_BRANDS.custom_mcp;

  const haystack = [
    connector.name,
    connector.provider,
    connector.transport,
    connector.server_url ?? "",
    connector.tool_name ?? "",
    connector.input_mapper,
    connector.result_mapper,
    connector.allowed_tools.join(" "),
  ].join(" ");

  return providerBrandFromText(haystack) ?? PROVIDER_BRANDS.custom_mcp;
}

export function ProviderBadge({
  brand,
  size = "md",
  showName = true,
}: {
  brand: ProviderBrand;
  size?: "sm" | "md" | "lg";
  showName?: boolean;
}) {
  const logoSize = size === "lg" ? "h-9 w-9" : size === "sm" ? "h-5 w-5" : "h-7 w-7";
  const shellSize = size === "lg" ? "h-12 w-12" : size === "sm" ? "h-7 w-7" : "h-10 w-10";

  return (
    <span className="inline-flex items-center gap-2">
      <span
        className={cn(
          "inline-flex shrink-0 items-center justify-center rounded-xl border border-[var(--color-border)] bg-gradient-to-br p-1 shadow-[var(--shadow-soft)]",
          shellSize,
          brand.accentClass,
        )}
      >
        <img src={brand.logoSrc} alt="" aria-hidden="true" className={cn("object-contain", logoSize)} />
      </span>
      {showName && <span className="font-medium text-fg">{brand.name}</span>}
    </span>
  );
}

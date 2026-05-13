/**
 * BrandMark — official logo glyphs for the brands Prism integrates with.
 *
 * Sources:
 *   - Arc        : web3icons (raw-svgs/networks/branded/arc.svg) — branded gradient
 *   - USDC/Circle: web3icons (raw-svgs/tokens/branded/USDC.svg) — official Circle blue
 *   - Polymarket : official 512px app-icon PNG → /public/polymarket-logo.png
 *                  (the homepage wordmark didn't tessellate cleanly at small
 *                  sizes; the square mark reads better next to other brand
 *                  glyphs in the tech stack and footers)
 *   - Coinbase   : simple-icons (CC0) — wordmark, currentColor
 *   - Neon       : simple-icons (CC0) — bolt mark, currentColor
 *   - IPFS       : simple-icons (CC0) — cube mark, currentColor
 *   - Ethereum   : simple-icons (CC0) — diamond mark, currentColor
 *   - GitHub     : simple-icons (CC0) — octocat, currentColor
 *   - Canteen    : official PNG sourced from thecanteenapp.com → /public/canteen-logo.png
 *
 * `branded` glyphs keep their brand colors. `mono` glyphs inherit text color
 * via `currentColor`, so they pick up the parent's text styling.
 *
 * Usage:
 *   <BrandMark name="arc" />
 *   <BrandMark name="circle" size={20} />
 *   <BrandMark name="canteen" size={24} aria-label="Canteen" />
 */

import { cn } from "@/lib/utils";

type BrandName =
  | "arc"
  | "circle"
  | "canteen"
  | "polymarket"
  | "coinbase"
  | "neon"
  | "ipfs"
  | "ethereum"
  | "github";

interface BrandMarkProps {
  name: BrandName;
  size?: number;
  className?: string;
  "aria-label"?: string;
  /** Render the brand at its native color (default for branded glyphs). */
  branded?: boolean;
}

/* ─────────────── Branded (keep brand colors) ─────────────── */

function ArcMark({ size = 16, className }: { size: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M3.5 20.9988C3.64596 16.5923 4.39308 12.48 5.64212 9.28212C7.22346 5.23096 9.51327 3 12.0881 3C14.6629 3 16.9527 5.23096 18.5346 9.28269C19.3573 11.3896 19.9625 13.8935 20.3213 16.6171C20.3537 16.8606 20.3808 17.1075 20.4085 17.3544C20.4177 17.3694 20.4229 17.3838 20.4212 17.3954C20.4212 17.3954 20.6317 18.7119 20.6767 20.9994H20.6531C20.3404 20.7427 16.6533 17.846 10.5413 18.6848C10.6337 17.6504 10.7606 16.6442 10.9244 15.6796C10.9331 15.6306 10.9423 15.5827 10.951 15.5337C13.3481 15.4615 15.4463 15.7396 17.0554 16.1048C17.0496 16.0667 17.0444 16.0275 17.0381 15.9894C16.7075 13.9298 16.2194 12.0444 15.59 10.4331C14.5613 7.79827 13.2188 6.16154 12.0875 6.16154C10.9562 6.16154 9.61365 7.79827 8.585 10.4331C8.33577 11.0706 8.10904 11.7502 7.90596 12.4667C7.62038 13.4712 7.38038 14.5483 7.18827 15.6796C6.90442 17.351 6.72731 19.1429 6.66212 21H3.5V20.9988Z"
        fill="url(#prism-brand-arc-gradient)"
      />
      <defs>
        <linearGradient
          id="prism-brand-arc-gradient"
          x1="12.0884"
          y1="3"
          x2="12.0884"
          y2="21"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#182680" />
          <stop offset="1" stopColor="#842D56" />
        </linearGradient>
      </defs>
    </svg>
  );
}

function CircleMark({ size = 16, className }: { size: number; className?: string }) {
  // USDC mark — Circle's flagship product and primary brand glyph for them
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M12 21C16.9706 21 21 16.9706 21 12C21 7.02943 16.9706 3 12 3C7.02943 3 3 7.02943 3 12C3 16.9706 7.02943 21 12 21Z"
        fill="#2775CA"
      />
      <path
        d="M13.6201 5.45V6.60874C15.9319 7.30624 17.625 9.45495 17.625 12.003C17.625 14.5511 15.9319 16.6999 13.6201 17.3973V18.5561C16.5675 17.8361 18.75 15.1755 18.75 12.003C18.75 8.83059 16.5675 6.16999 13.6201 5.45Z"
        fill="white"
      />
      <path
        d="M6.37499 12.003C6.37499 9.45495 8.06809 7.30624 10.3799 6.60874V5.45C7.43247 6.16999 5.25 8.83059 5.25 12.003C5.25 15.1755 7.43247 17.8361 10.3799 18.5561V17.3973C8.06809 16.7055 6.37499 14.5511 6.37499 12.003Z"
        fill="white"
      />
      <path
        d="M14.4188 13.2575C14.4188 10.9569 10.8132 11.9019 10.8132 10.6306C10.8132 10.175 11.1788 9.8825 11.8763 9.8825C12.7088 9.8825 12.9957 10.2875 13.0857 10.8331H14.2331C14.1308 9.80916 13.5431 9.16262 12.5626 8.97002V8.06565H11.4376V8.93774C10.3634 9.07454 9.6882 9.70009 9.6882 10.6306C9.6882 12.9425 13.2994 12.0762 13.2994 13.325C13.2994 13.7974 12.8438 14.1124 12.0732 14.1124C11.0663 14.1124 10.7344 13.6681 10.6107 13.055H9.49133C9.56385 14.1765 10.2554 14.8784 11.4376 15.0536V15.9405H12.5626V15.0654C13.7163 14.9164 14.4188 14.2452 14.4188 13.2575Z"
        fill="white"
      />
    </svg>
  );
}

function CanteenMark({
  size = 16,
  className,
}: {
  size: number;
  className?: string;
}) {
  // Canteen is the team behind Arc — official logo PNG served from /public.
  // Using <img> rather than next/image because: (a) it's tiny (13KB), (b) we
  // want predictable inline sizing matching other SVG marks, (c) it sits
  // alongside <svg> siblings so the natural HTML element keeps render parity.
  return (
    <img
      src="/canteen-logo.png"
      alt=""
      width={size}
      height={size}
      className={cn("inline-block object-contain", className)}
      aria-hidden="true"
    />
  );
}

/* ─────────────── Mono (currentColor) ─────────────── */

function PolymarketMark({
  size = 16,
  className,
}: {
  size: number;
  className?: string;
}) {
  // Official Polymarket app icon — square mark, white triangles on blue.
  // Using <img> rather than <Image> for sizing parity with other inline glyphs.
  return (
    <img
      src="/polymarket-logo.png"
      alt=""
      width={size}
      height={size}
      className={cn("inline-block object-contain rounded-[2px]", className)}
      aria-hidden="true"
    />
  );
}

function CoinbaseMark({
  size = 16,
  className,
}: {
  size: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12C24 5.4 18.66 0 12 0zm0 19.2c-4 0-7.2-3.2-7.2-7.2S8 4.8 12 4.8c3.5 0 6.4 2.6 7.06 6h-4.86c-.5-1-1.6-1.7-2.86-1.7-1.7 0-3.16 1.36-3.16 3.06s1.46 3.16 3.16 3.16c1.26 0 2.36-.7 2.86-1.7h4.86C18.4 16.6 15.5 19.2 12 19.2z" />
    </svg>
  );
}

function NeonMark({
  size = 16,
  className,
}: {
  size: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path d="M24 0V24l-9.365-8.045V24H0V0ZM2.942 21.087h8.751V9.563l9.365 8.204V2.919L2.942 2.914Z" />
    </svg>
  );
}

function IpfsMark({
  size = 16,
  className,
}: {
  size: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path d="M12 0L1.608 6v12L12 24l10.392-6V6zm-1.073 1.445h.001a1.8 1.8 0 002.138 0l7.534 4.35a1.794 1.794 0 000 .403l-7.535 4.35a1.8 1.8 0 00-2.137 0l-7.536-4.35a1.795 1.795 0 000-.402zM21.324 7.4c.109.08.226.147.349.201v8.7a1.8 1.8 0 00-1.069 1.852l-7.535 4.35a1.8 1.8 0 00-.349-.2l-.009-8.653a1.8 1.8 0 001.07-1.851zm-18.648.048l7.535 4.35a1.8 1.8 0 001.069 1.852v8.7c-.124.054-.24.122-.349.202l-7.535-4.35a1.8 1.8 0 00-1.069-1.852v-8.7c.124-.054.24-.122.35-.202z" />
    </svg>
  );
}

function EthereumMark({
  size = 16,
  className,
}: {
  size: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path d="M11.944 17.97L4.58 13.62 11.943 24l7.37-10.38-7.372 4.35h.003zM12.056 0L4.69 12.223l7.365 4.354 7.365-4.35L12.056 0z" />
    </svg>
  );
}

function GithubMark({
  size = 16,
  className,
}: {
  size: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}

/* ─────────────── Public component ─────────────── */

export function BrandMark({
  name,
  size = 16,
  className,
  "aria-label": ariaLabel,
}: BrandMarkProps) {
  const inner = (() => {
    switch (name) {
      case "arc":
        return <ArcMark size={size} className={className} />;
      case "circle":
        return <CircleMark size={size} className={className} />;
      case "canteen":
        return <CanteenMark size={size} className={className} />;
      case "polymarket":
        return <PolymarketMark size={size} className={className} />;
      case "coinbase":
        return <CoinbaseMark size={size} className={className} />;
      case "neon":
        return <NeonMark size={size} className={className} />;
      case "ipfs":
        return <IpfsMark size={size} className={className} />;
      case "ethereum":
        return <EthereumMark size={size} className={className} />;
      case "github":
        return <GithubMark size={size} className={className} />;
    }
  })();

  // Accessibility: when an aria-label is provided, wrap with role=img so
  // screen readers announce it. Otherwise the inner SVG stays aria-hidden.
  if (ariaLabel) {
    return (
      <span role="img" aria-label={ariaLabel} className="inline-flex items-center">
        {inner}
      </span>
    );
  }
  return inner;
}

/* Re-export individual marks for tree-shaking when only one is needed. */
export {
  ArcMark,
  CircleMark,
  CanteenMark,
  PolymarketMark,
  CoinbaseMark,
  NeonMark,
  IpfsMark,
  EthereumMark,
  GithubMark,
};

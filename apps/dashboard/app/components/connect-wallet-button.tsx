"use client";

/**
 * ConnectWalletButton — renders the Reown AppKit connect button.
 *
 * Uses the `<w3m-button>` custom element registered by `createAppKit()`
 * inside the Web3Provider. This element automatically opens the Reown
 * modal with social login, email, and wallet-connect options.
 *
 * The button is keyboard-focusable by default (Web Component with
 * internal focus management) and responsive down to 44px hit-target.
 *
 * VAL-WALLET-009: The w3m-button renders at 30px height on mobile (375px
 * viewport), below the 32px minimum hit target. A wrapper div with
 * min-h-[32px] min-w-[32px] enforces the accessible minimum without
 * overriding the Web Component's internal styles.
 */

/* eslint-disable next/inline-script -- not a script, just JSX for a custom element */

export function ConnectWalletButton() {
  return (
    <div className="min-h-[32px] min-w-[32px]">
      <w3m-button
        balance="hide"
        size="sm"
        // The `label` attribute sets the disconnected-state text.
        label="Connect"
      />
    </div>
  );
}

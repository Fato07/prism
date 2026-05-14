import { defineChain } from "@reown/appkit/networks";

/** ERC-8004 contract addresses on Arc Testnet (chain 5042002). */
export const ARC_TESTNET_CHAIN_ID = 5042002;

export const CONTRACTS = {
  IdentityRegistry: "0x8004A818BFB912233c491871b3d84c89A494BD9e",
  ReputationRegistry: "0x8004B663056A597Dffe9eCcC1965A193B7388713",
  ValidationRegistry: "0x8004Cb1BF31DAf7788923b405b754f57acEB4272",
  AgenticCommerce: "0x0747EEf0706327138c69792bF28Cd525089e4583",
  USDC: "0x3600000000000000000000000000000000000000",
} as const;

/** Arc Testnet viem-compatible chain definition for Reown/wagmi. */
export const arcTestnet = defineChain({
  id: 5042002, // from packages/arc-contracts
  caipNetworkId: "eip155:5042002",
  chainNamespace: "eip155",
  name: "Arc Testnet",
  nativeCurrency: { decimals: 6, name: "USDC", symbol: "USDC" }, // USDC IS the gas token
  rpcUrls: {
    default: { http: [process.env.NEXT_PUBLIC_ARC_RPC_URL!] },
  },
  blockExplorers: {
    default: {
      name: "Arc Explorer",
      url: "https://explorer.testnet.arc-node.thecanteenapp.com",
    },
  },
  contracts: {
    // USDC native: '0x3600000000000000000000000000000000000000'
    // IdentityRegistry: '0x8004A818BFB912233c491871b3d84c89A494BD9e'
    // ValidationRegistry: '0x8004Cb1BF31DAf7788923b405b754f57acEB4272'
  },
});

/**
 * USYC contract address on Arc Testnet (env-driven, may be undefined).
 * When undefined the trader treasury module ships in dry_run mode.
 */
export const USYC_ARC_TESTNET_ADDRESS: string | undefined =
  process.env.USYC_ARC_TESTNET_ADDRESS || undefined;

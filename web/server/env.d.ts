// The parts of the Cloudflare Pages Functions runtime used here (instead of pulling @cloudflare/workers-types).
interface D1Result<T = unknown> { results: T[]; success: boolean; meta: { changes?: number } }
interface D1PreparedStatement {
  bind(...values: unknown[]): D1PreparedStatement;
  first<T = unknown>(): Promise<T | null>;
  run(): Promise<D1Result>;
  all<T = unknown>(): Promise<D1Result<T>>;
}
interface D1Database { prepare(query: string): D1PreparedStatement; batch(statements: D1PreparedStatement[]): Promise<D1Result[]> }

interface Env {
  DB: D1Database;
  PUSH_SECRET: string;      // shared with the agents' host: signs /api/internal/push
  SESSION_SECRET: string;   // signs the dashboard session tokens
  BUILDER_CODE?: string;    // Smart Flow builder code on Strike (empty: real trading not offered yet)
  LIVE_ENV?: string;        // "testnet" only on the QA site: Preprod wallets + Strike testnet. Default: mainnet
  BUILDER_FEE_BPS?: string; // fee the user approves at builder connect (20 = 0.20 % per execution)
  LIVE_ALLOW?: string;      // invite-only real trading: comma-separated wallet addresses (a Pages secret). Unset: everyone
  ADMIN_IDS?: string;       // agents whose owners read the site's suggestions (comma-separated ids; My agent shows the inbox)
}

interface Ctx { request: Request; env: Env; params: Record<string, string | string[]>; waitUntil(p: Promise<unknown>): void }

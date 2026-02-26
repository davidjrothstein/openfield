/**
 * Provider registry.
 *
 * To add a new provider:
 *   1. Implement EmailProvider in providers/<name>.ts
 *   2. Import and register it in the PROVIDERS map below
 *   3. That's it — the rest of the application discovers providers through
 *      this registry, so no other files need to change.
 *
 * See CLAUDE.md for the full provider development guide.
 */

import { GmailProvider } from "./gmail"
import type { EmailProvider } from "./interface"

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

const PROVIDERS: Record<string, EmailProvider> = {
  gmail: new GmailProvider(),
  // office365: new Office365Provider(),
  // exchange:  new ExchangeProvider(),
  // icloud:    new ICloudProvider(),
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

/** Returns the provider for a given ID, or null if unknown. */
export function getProvider(id: string): EmailProvider | null {
  return PROVIDERS[id] ?? null
}

/** Returns all registered providers (useful for a "Connect account" UI). */
export function listProviders(): EmailProvider[] {
  return Object.values(PROVIDERS)
}

export type { EmailProvider }
export type { Email, TokenSet, AuthInfo, ListEmailsOptions } from "./interface"

/**
 * OpenField Email Provider Interface
 *
 * All email providers (Gmail, Office 365, Exchange, iCloud, etc.) must implement
 * the EmailProvider interface. Providers are registered at startup and resolved
 * by name at runtime.
 *
 * To add a new provider:
 *   1. Create providers/<name>.ts implementing EmailProvider
 *   2. Import and call registerProvider() from that file
 *   3. Import the file in providers/index.ts (bottom of this file)
 *
 * See CLAUDE.md for the full provider specification.
 */

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export interface Attachment {
  name: string
  size: string
  type: string
  mimeType?: string
  attachmentId?: string
}

/**
 * Canonical email message shape used throughout OpenField.
 * Providers must map their native format to this interface.
 */
export interface EmailMessage {
  id: string
  threadId?: string
  sender: string
  senderEmail: string
  senderTitle?: string
  senderCompany?: string
  lastInteraction?: string
  subject: string
  preview: string
  body: string[]
  timestamp: string
  read: boolean
  flagged: boolean
  folder: string
  attachments: Attachment[]
  actionRequired?: boolean
  priority?: boolean
  priorityReason?: string
  actions?: { text: string; id: string; type: 'reply' | 'todo' }[]
  keyDetails?: { label: string; value: string }[]
  threadSummary?: string[]
  isDistributionList?: boolean
}

export interface Folder {
  id: string
  name: string
  displayName: string
  count?: number
  unreadCount?: number
}

export interface SendEmailOptions {
  to: string | string[]
  cc?: string | string[]
  bcc?: string | string[]
  subject: string
  body: string
  replyToId?: string
  threadId?: string
}

export interface QueryOptions {
  maxResults?: number
  pageToken?: string
  query?: string
  after?: Date
  before?: Date
}

export interface AuthOptions {
  redirectUri?: string
  scopes?: string[]
  state?: string
}

/**
 * Token bundle returned after OAuth exchange or refresh.
 * Providers may include extra fields but must supply accessToken.
 */
export interface AuthTokens {
  provider: string
  accessToken: string
  refreshToken?: string
  expiresAt?: number
  userEmail?: string
  scope?: string
}

// ---------------------------------------------------------------------------
// Core provider interface
// ---------------------------------------------------------------------------

/**
 * Every email provider must implement this interface.
 * Methods that require API calls accept AuthTokens as the first argument
 * (server-side callers retrieve tokens from the secure cookie store and pass
 * them through — the provider itself never reads cookies).
 */
export interface EmailProvider {
  /** Stable machine-readable identifier, e.g. "gmail" */
  readonly name: string
  /** Human-readable display name, e.g. "Gmail" */
  readonly displayName: string

  // --- Auth ---

  /**
   * Returns the URL the user should be redirected to in order to grant
   * permission. Called server-side; no tokens required.
   */
  getAuthUrl(options?: AuthOptions): string

  /**
   * Exchanges a one-time authorization code for a set of tokens.
   * Called from the OAuth callback API route.
   */
  exchangeCodeForTokens(code: string, redirectUri: string): Promise<AuthTokens>

  /**
   * Refreshes an expired access token using a stored refresh token.
   * Implementations should update expiresAt on the returned tokens.
   */
  refreshTokens(tokens: AuthTokens): Promise<AuthTokens>

  /**
   * Returns true if the supplied tokens are valid and not expired.
   * Providers may perform a lightweight API check or inspect expiresAt.
   */
  isAuthenticated(tokens: AuthTokens): Promise<boolean>

  // --- Folders ---

  /** Lists all folders/labels available in the account. */
  getFolders(tokens: AuthTokens): Promise<Folder[]>

  // --- Reading ---

  /**
   * Fetches a page of emails for the specified folder key.
   * Folder keys must map to the values used in EmailMessage.folder.
   */
  getEmails(
    tokens: AuthTokens,
    folder?: string,
    options?: QueryOptions
  ): Promise<EmailMessage[]>

  /** Fetches a single email by its provider-specific ID. */
  getEmail(tokens: AuthTokens, id: string): Promise<EmailMessage>

  // --- Mutations ---

  sendEmail(tokens: AuthTokens, email: SendEmailOptions): Promise<void>
  markAsRead(tokens: AuthTokens, ids: string[]): Promise<void>
  markAsUnread(tokens: AuthTokens, ids: string[]): Promise<void>
  archiveEmails(tokens: AuthTokens, ids: string[]): Promise<void>
  deleteEmails(tokens: AuthTokens, ids: string[]): Promise<void>
}

// ---------------------------------------------------------------------------
// Provider registry
// ---------------------------------------------------------------------------

const registry = new Map<string, EmailProvider>()

export function registerProvider(provider: EmailProvider): void {
  registry.set(provider.name, provider)
}

/**
 * Resolves a provider by name. Throws if not found.
 * Use getRegisteredProviders() to enumerate what is available.
 */
export function getProvider(name: string): EmailProvider {
  const provider = registry.get(name)
  if (!provider) {
    const available = [...registry.keys()].join(', ') || 'none'
    throw new Error(
      `Unknown email provider: "${name}". Registered providers: ${available}`
    )
  }
  return provider
}

/** Returns the names of all registered providers. */
export function getRegisteredProviders(): string[] {
  return [...registry.keys()]
}

// ---------------------------------------------------------------------------
// Register built-in providers
// ---------------------------------------------------------------------------
// Import each provider module here. The module calls registerProvider()
// as a side-effect on import.

import './gmail'
import './mock'

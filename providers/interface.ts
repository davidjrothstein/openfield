/**
 * Core email provider interface.
 *
 * Every provider (Gmail, Office 365, Exchange, iCloud, …) must implement
 * EmailProvider. The rest of the application only depends on this interface —
 * swap providers by changing the factory in providers/index.ts.
 *
 * The Email type here is intentionally identical to the one in
 * lib/email-data.ts so existing UI components work without modification.
 */

// ---------------------------------------------------------------------------
// Email data model (mirrors lib/email-data.ts — must stay in sync)
// ---------------------------------------------------------------------------

export interface Email {
  id: string
  sender: string
  senderEmail: string
  /** Job title of the sender (may be empty for providers that don't expose it) */
  senderTitle: string
  /** Company / domain of the sender */
  senderCompany: string
  /** Human-readable date of last interaction */
  lastInteraction: string
  subject: string
  /** Short preview / snippet shown in the email list */
  preview: string
  /** Human-readable timestamp for the list (e.g. "2:14 PM", "Yesterday") */
  timestamp: string
  read: boolean
  flagged: boolean
  actionRequired: boolean
  /** Folder key: "inbox" | "sent" | "drafts" | "spam" | "trash" */
  folder: string
  /** Full body as an array of paragraphs */
  body: string[]
  /** AI-suggested actions (populated by a separate enrichment step) */
  actions: EmailAction[]
  keyDetails: KeyDetail[]
  /** AI-generated thread summary (populated by a separate enrichment step) */
  threadSummary: string[]
  attachments: Attachment[]
  priority: boolean
  priorityReason?: string
  isDistributionList?: boolean
}

export interface EmailAction {
  text: string
  id: string
  type: "reply" | "todo"
}

export interface KeyDetail {
  label: string
  value: string
}

export interface Attachment {
  name: string
  /** Human-readable size, e.g. "2.3 MB" */
  size: string
  /** MIME type, e.g. "application/pdf" */
  type: string
}

// ---------------------------------------------------------------------------
// Auth types
// ---------------------------------------------------------------------------

/**
 * OAuth token set returned by the provider after a successful code exchange or
 * refresh. Stored in the encrypted server-side session; never touches the
 * client.
 */
export interface TokenSet {
  access_token: string
  refresh_token?: string
  /** Unix epoch in milliseconds */
  expiry_date?: number
  token_type?: string
  scope?: string
}

/** Basic profile information returned alongside the token set. */
export interface AuthInfo {
  userEmail: string
  userName: string
}

// ---------------------------------------------------------------------------
// Query options
// ---------------------------------------------------------------------------

export interface ListEmailsOptions {
  /** Folder key (inbox, sent, drafts, …). Defaults to "inbox". */
  folder?: string
  /** Maximum number of messages to return. Defaults to 25. */
  maxResults?: number
  /** Pagination cursor returned by the previous call. */
  pageToken?: string
  /** Provider-native search query string. */
  query?: string
}

// ---------------------------------------------------------------------------
// Provider contract
// ---------------------------------------------------------------------------

/**
 * Every email provider adapter must satisfy this interface.
 *
 * Stateless by design — all per-user state (tokens) is passed as arguments
 * so the same provider instance can be reused across requests in a serverless
 * environment, and later reused inside an Electron main process.
 */
export interface EmailProvider {
  /** Stable machine identifier, e.g. "gmail", "office365" */
  readonly id: string
  /** Human-readable display name, e.g. "Gmail" */
  readonly name: string
  /** Path to a public icon asset (optional) */
  readonly icon?: string

  // ------------------------------------------------------------------
  // OAuth lifecycle
  // ------------------------------------------------------------------

  /**
   * Build the authorization URL that the user is redirected to in order to
   * grant the application access.
   *
   * @param redirectUri  The URI Google/Microsoft/etc. will redirect to after
   *                     the user grants (or denies) access.
   * @param state        Optional opaque value echoed back by the provider in
   *                     the callback. Useful for CSRF protection or encoding
   *                     the provider ID.
   */
  getAuthUrl(redirectUri: string, state?: string): string

  /**
   * Exchange a one-time authorization code for access + refresh tokens.
   *
   * @param code         The code received in the OAuth callback query string.
   * @param redirectUri  Must match the URI used in getAuthUrl exactly.
   */
  exchangeCode(code: string, redirectUri: string): Promise<TokenSet>

  /**
   * Use the refresh token to obtain a fresh access token.
   * Returns the updated TokenSet (the refresh token is usually unchanged).
   */
  refreshTokens(tokens: TokenSet): Promise<TokenSet>

  /** Fetch the authenticated user's profile (email + display name). */
  getUserInfo(tokens: TokenSet): Promise<AuthInfo>

  // ------------------------------------------------------------------
  // Email operations
  // ------------------------------------------------------------------

  /**
   * List emails, mapping provider-native message format to the canonical
   * Email interface so UI components remain provider-agnostic.
   */
  listEmails(tokens: TokenSet, options?: ListEmailsOptions): Promise<Email[]>

  /**
   * Fetch a single email by its provider-native ID.
   * Used to refresh stale list entries or pre-fetch on hover.
   */
  getEmail(tokens: TokenSet, id: string): Promise<Email>

  /** Mark an email as read. */
  markAsRead(tokens: TokenSet, id: string): Promise<void>
}

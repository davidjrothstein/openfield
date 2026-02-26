/**
 * Gmail provider — first concrete implementation of EmailProvider.
 *
 * Uses the Google APIs Node.js client (googleapis) for all Gmail interactions.
 * The OAuth2 client is created fresh per call so this module is stateless and
 * safe to use in a Next.js serverless environment or an Electron main process.
 *
 * Scopes requested:
 *   - gmail.readonly          — read emails & labels
 *   - gmail.modify            — mark as read (modify label UNREAD)
 *   - userinfo.email          — get authenticated user's email address
 *   - userinfo.profile        — get display name
 */

import { google } from "googleapis"
import type { gmail_v1 } from "googleapis"
import type {
  EmailProvider,
  Email,
  TokenSet,
  AuthInfo,
  ListEmailsOptions,
  Attachment,
  KeyDetail,
} from "./interface"

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SCOPES = [
  "https://www.googleapis.com/auth/gmail.readonly",
  "https://www.googleapis.com/auth/gmail.modify",
  "https://www.googleapis.com/auth/userinfo.email",
  "https://www.googleapis.com/auth/userinfo.profile",
]

/** Maps our folder keys to Gmail label IDs */
const FOLDER_TO_LABEL: Record<string, string> = {
  inbox: "INBOX",
  sent: "SENT",
  drafts: "DRAFT",
  spam: "SPAM",
  trash: "TRASH",
}

// ---------------------------------------------------------------------------
// Provider implementation
// ---------------------------------------------------------------------------

export class GmailProvider implements EmailProvider {
  readonly id = "gmail"
  readonly name = "Gmail"
  readonly icon = "/icons/gmail.svg"

  // ------------------------------------------------------------------
  // OAuth helpers
  // ------------------------------------------------------------------

  private createOAuthClient(redirectUri?: string) {
    return new google.auth.OAuth2(
      process.env.GOOGLE_CLIENT_ID,
      process.env.GOOGLE_CLIENT_SECRET,
      redirectUri,
    )
  }

  getAuthUrl(redirectUri: string, state?: string): string {
    const client = this.createOAuthClient(redirectUri)
    return client.generateAuthUrl({
      access_type: "offline",
      scope: SCOPES,
      // Force consent so we always get a refresh token, even on re-auth
      prompt: "consent",
      state,
    })
  }

  async exchangeCode(code: string, redirectUri: string): Promise<TokenSet> {
    const client = this.createOAuthClient(redirectUri)
    const { tokens } = await client.getToken(code)
    return tokens as TokenSet
  }

  async refreshTokens(tokens: TokenSet): Promise<TokenSet> {
    const client = this.createOAuthClient()
    client.setCredentials(tokens)
    const { credentials } = await client.refreshAccessToken()
    // Preserve the refresh token if the provider didn't return a new one
    return {
      ...credentials,
      refresh_token: credentials.refresh_token ?? tokens.refresh_token,
    } as TokenSet
  }

  async getUserInfo(tokens: TokenSet): Promise<AuthInfo> {
    const client = this.createOAuthClient()
    client.setCredentials(tokens)
    const oauth2 = google.oauth2({ version: "v2", auth: client })
    const { data } = await oauth2.userinfo.get()
    return {
      userEmail: data.email ?? "",
      userName: data.name ?? data.email ?? "",
    }
  }

  // ------------------------------------------------------------------
  // Email operations
  // ------------------------------------------------------------------

  async listEmails(tokens: TokenSet, options: ListEmailsOptions = {}): Promise<Email[]> {
    const client = this.createOAuthClient()
    client.setCredentials(tokens)
    const gmail = google.gmail({ version: "v1", auth: client })

    const labelIds = options.folder
      ? [FOLDER_TO_LABEL[options.folder] ?? "INBOX"]
      : ["INBOX"]

    const listRes = await gmail.users.messages.list({
      userId: "me",
      maxResults: options.maxResults ?? 25,
      labelIds,
      q: options.query,
      pageToken: options.pageToken,
    })

    const messageRefs = listRes.data.messages ?? []
    if (messageRefs.length === 0) return []

    // Fetch full message objects in parallel (concurrency capped by JS event loop)
    const emails = await Promise.all(
      messageRefs.map(({ id }) => this.fetchMessage(gmail, id!)),
    )

    return emails.filter((e): e is Email => e !== null)
  }

  async getEmail(tokens: TokenSet, id: string): Promise<Email> {
    const client = this.createOAuthClient()
    client.setCredentials(tokens)
    const gmail = google.gmail({ version: "v1", auth: client })
    const email = await this.fetchMessage(gmail, id)
    if (!email) throw new Error(`Email ${id} not found`)
    return email
  }

  async markAsRead(tokens: TokenSet, id: string): Promise<void> {
    const client = this.createOAuthClient()
    client.setCredentials(tokens)
    const gmail = google.gmail({ version: "v1", auth: client })
    await gmail.users.messages.modify({
      userId: "me",
      id,
      requestBody: { removeLabelIds: ["UNREAD"] },
    })
  }

  // ------------------------------------------------------------------
  // Private helpers
  // ------------------------------------------------------------------

  private async fetchMessage(
    gmail: gmail_v1.Gmail,
    id: string,
  ): Promise<Email | null> {
    try {
      const res = await gmail.users.messages.get({
        userId: "me",
        id,
        format: "full",
      })
      return this.mapMessageToEmail(res.data)
    } catch {
      return null
    }
  }

  private mapMessageToEmail(message: gmail_v1.Schema$Message): Email {
    const headers: gmail_v1.Schema$MessagePartHeader[] =
      message.payload?.headers ?? []

    const getHeader = (name: string) =>
      headers.find((h) => h.name?.toLowerCase() === name.toLowerCase())?.value ?? ""

    const fromRaw = getHeader("From")
    const { name: senderName, email: senderEmail } = parseAddress(fromRaw)

    const labelIds: string[] = message.labelIds ?? []
    const folder = resolveFolder(labelIds)
    const isDistributionList = detectDistributionList(headers)

    const internalDate = parseInt(message.internalDate ?? "0", 10)

    // Extract full body text
    const bodyText = extractText(message.payload ?? {})
    const bodyParagraphs = bodyText
      .split(/\n{2,}/)
      .map((s) => s.trim())
      .filter(Boolean)

    // Build key details from headers
    const keyDetails: KeyDetail[] = [
      { label: "From", value: fromRaw },
      { label: "To", value: getHeader("To") },
      { label: "Date", value: getHeader("Date") },
    ]
    const cc = getHeader("Cc")
    if (cc) keyDetails.push({ label: "CC", value: cc })

    // Attachments
    const attachments = extractAttachments(message.payload ?? {})

    return {
      id: message.id ?? "",
      sender: senderName,
      senderEmail,
      senderTitle: "",
      senderCompany: domainOf(senderEmail),
      lastInteraction: formatDate(internalDate),
      subject: getHeader("Subject") || "(no subject)",
      preview: message.snippet ?? "",
      timestamp: formatTimestamp(internalDate),
      read: !labelIds.includes("UNREAD"),
      flagged: labelIds.includes("STARRED"),
      actionRequired: false, // enriched separately by AI layer
      folder,
      body: bodyParagraphs.length > 0 ? bodyParagraphs : [message.snippet ?? ""],
      actions: [], // enriched separately by AI layer
      keyDetails,
      threadSummary: [], // enriched separately by AI layer
      attachments,
      priority: labelIds.includes("IMPORTANT"),
      isDistributionList,
    }
  }
}

// ---------------------------------------------------------------------------
// Pure utility functions (no I/O)
// ---------------------------------------------------------------------------

/** Parse "Display Name <email@example.com>" or "email@example.com" */
function parseAddress(raw: string): { name: string; email: string } {
  const match = raw.match(/^(?:"?([^"<]+?)"?\s+)?<([^>]+)>$/)
  if (match) {
    return {
      name: match[1]?.trim() || match[2],
      email: match[2].trim(),
    }
  }
  return { name: raw.trim(), email: raw.trim() }
}

function domainOf(email: string): string {
  const at = email.indexOf("@")
  return at >= 0 ? email.slice(at + 1) : email
}

function resolveFolder(labelIds: string[]): string {
  if (labelIds.includes("SENT")) return "sent"
  if (labelIds.includes("DRAFT")) return "drafts"
  if (labelIds.includes("SPAM")) return "spam"
  if (labelIds.includes("TRASH")) return "trash"
  return "inbox"
}

function detectDistributionList(headers: gmail_v1.Schema$MessagePartHeader[]): boolean {
  const relevant = ["list-id", "list-unsubscribe", "precedence", "x-mailer"]
  for (const h of headers) {
    const name = h.name?.toLowerCase() ?? ""
    if (relevant.includes(name)) {
      if (name === "precedence" && h.value?.toLowerCase().includes("bulk")) return true
      if (name === "list-id" || name === "list-unsubscribe") return true
    }
  }
  return false
}

/**
 * Recursively extract plain text from a MIME payload.
 * Prefers text/plain; falls back to text/html with tag stripping.
 */
function extractText(payload: gmail_v1.Schema$MessagePart): string {
  const mime = payload.mimeType ?? ""

  if (mime === "text/plain" && payload.body?.data) {
    return decodeBase64url(payload.body.data)
  }

  if (mime === "text/html" && payload.body?.data) {
    return stripHtml(decodeBase64url(payload.body.data))
  }

  if (payload.parts && payload.parts.length > 0) {
    if (mime === "multipart/alternative") {
      const plain = payload.parts.find((p) => p.mimeType === "text/plain")
      if (plain) return extractText(plain)
      const html = payload.parts.find((p) => p.mimeType === "text/html")
      if (html) return extractText(html)
    }
    return payload.parts
      .map((p) => extractText(p))
      .filter(Boolean)
      .join("\n\n")
  }

  return ""
}

function extractAttachments(payload: gmail_v1.Schema$MessagePart): Attachment[] {
  const results: Attachment[] = []

  function walk(part: gmail_v1.Schema$MessagePart) {
    if (part.filename && part.body?.attachmentId) {
      results.push({
        name: part.filename,
        size: formatBytes(part.body.size ?? 0),
        type: part.mimeType ?? "application/octet-stream",
      })
    }
    part.parts?.forEach(walk)
  }

  walk(payload)
  return results
}

function decodeBase64url(data: string): string {
  // Gmail uses URL-safe base64; Buffer handles both variants
  return Buffer.from(data, "base64url").toString("utf-8")
}

function stripHtml(html: string): string {
  return html
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s{2,}/g, " ")
    .trim()
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B"
  const units = ["B", "KB", "MB", "GB"]
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

/** "2:14 PM" for today, "Mon" for this week, "Mar 5" for older */
function formatTimestamp(ms: number): string {
  if (!ms) return ""
  const date = new Date(ms)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = diffMs / (1000 * 60 * 60 * 24)

  if (diffDays < 1 && date.getDate() === now.getDate()) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  }
  if (diffDays < 7) {
    return date.toLocaleDateString([], { weekday: "short" })
  }
  return date.toLocaleDateString([], { month: "short", day: "numeric" })
}

/** "Feb 14, 2026" */
function formatDate(ms: number): string {
  if (!ms) return ""
  return new Date(ms).toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

/**
 * Gmail provider — implements EmailProvider using the Google Gmail API v1.
 *
 * Required environment variables:
 *   GOOGLE_CLIENT_ID      — OAuth 2.0 client ID from Google Cloud Console
 *   GOOGLE_CLIENT_SECRET  — OAuth 2.0 client secret
 *   GOOGLE_REDIRECT_URI   — Must match exactly what is registered in GCP
 *                           (default: http://localhost:3000/api/auth/callback)
 */

import { google, gmail_v1 } from 'googleapis'
import {
  EmailProvider,
  EmailMessage,
  Folder,
  SendEmailOptions,
  QueryOptions,
  AuthOptions,
  AuthTokens,
  Attachment,
  registerProvider,
} from './index'

// ---------------------------------------------------------------------------
// Folder / label mapping
// ---------------------------------------------------------------------------

/** Maps OpenField folder keys → Gmail label IDs used in list queries */
const FOLDER_TO_LABEL: Record<string, string> = {
  inbox: 'INBOX',
  sent: 'SENT',
  drafts: 'DRAFT',
  spam: 'SPAM',
  trash: 'TRASH',
  priority: 'IMPORTANT',
  newsletters: 'CATEGORY_PROMOTIONS',
}

/** Reverse mapping for labelling fetched messages */
const LABEL_TO_FOLDER: Record<string, string> = {
  INBOX: 'inbox',
  SENT: 'sent',
  DRAFT: 'drafts',
  SPAM: 'spam',
  TRASH: 'trash',
  IMPORTANT: 'priority',
  CATEGORY_PROMOTIONS: 'newsletters',
}

// ---------------------------------------------------------------------------
// Helper: OAuth2 client
// ---------------------------------------------------------------------------

function createOAuthClient(redirectUri?: string) {
  return new google.auth.OAuth2(
    process.env.GOOGLE_CLIENT_ID,
    process.env.GOOGLE_CLIENT_SECRET,
    redirectUri ??
      process.env.GOOGLE_REDIRECT_URI ??
      'http://localhost:3000/api/auth/callback'
  )
}

// ---------------------------------------------------------------------------
// Helper: message parsing
// ---------------------------------------------------------------------------

function getHeader(headers: gmail_v1.Schema$MessagePartHeader[], name: string): string {
  return (
    headers.find((h) => h.name?.toLowerCase() === name.toLowerCase())?.value ?? ''
  )
}

function extractBody(payload: gmail_v1.Schema$MessagePart | undefined): string {
  if (!payload) return ''

  // Inline body data on this part
  if (payload.body?.data) {
    return Buffer.from(payload.body.data, 'base64url').toString('utf-8')
  }

  if (payload.parts) {
    // Prefer plain text, fall back to HTML
    const textPart = payload.parts.find((p) => p.mimeType === 'text/plain')
    const htmlPart = payload.parts.find((p) => p.mimeType === 'text/html')
    const chosen = textPart ?? htmlPart
    if (chosen?.body?.data) {
      return Buffer.from(chosen.body.data, 'base64url').toString('utf-8')
    }
    // Recurse into multipart containers (e.g. multipart/alternative)
    for (const part of payload.parts) {
      if (part.parts) {
        const nested = extractBody(part)
        if (nested) return nested
      }
    }
  }

  return ''
}

function extractAttachments(payload: gmail_v1.Schema$MessagePart | undefined): Attachment[] {
  const results: Attachment[] = []

  function traverse(part: gmail_v1.Schema$MessagePart) {
    if (part.filename && part.body?.attachmentId) {
      results.push({
        name: part.filename,
        size: formatBytes(part.body.size ?? 0),
        type: extensionToType(part.filename),
        mimeType: part.mimeType ?? undefined,
        attachmentId: part.body.attachmentId,
      })
    }
    part.parts?.forEach(traverse)
  }

  if (payload) traverse(payload)
  return results
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function extensionToType(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() ?? ''
  const map: Record<string, string> = {
    pdf: 'PDF', docx: 'Word', doc: 'Word', xlsx: 'Excel', xls: 'Excel',
    pptx: 'PowerPoint', ppt: 'PowerPoint', png: 'Image', jpg: 'Image',
    jpeg: 'Image', gif: 'Image', zip: 'Archive', rar: 'Archive',
    mp4: 'Video', mov: 'Video', mp3: 'Audio', wav: 'Audio',
  }
  return map[ext] ?? 'File'
}

function inferFolder(labelIds: string[]): string {
  for (const [label, folder] of Object.entries(LABEL_TO_FOLDER)) {
    if (labelIds.includes(label)) return folder
  }
  return 'inbox'
}

function parseSender(from: string): { sender: string; senderEmail: string } {
  const match = from.match(/^(.*?)\s*<(.+?)>$/)
  if (match) {
    return {
      sender: match[1].trim().replace(/^"|"$/g, ''),
      senderEmail: match[2].trim(),
    }
  }
  return { sender: from, senderEmail: from }
}

function toEmailMessage(msg: gmail_v1.Schema$Message): EmailMessage {
  const headers = msg.payload?.headers ?? []
  const labelIds = msg.labelIds ?? []
  const { sender, senderEmail } = parseSender(getHeader(headers, 'From'))
  const rawDate = getHeader(headers, 'Date')
  const timestamp = rawDate ? new Date(rawDate).toISOString() : new Date().toISOString()
  const body = extractBody(msg.payload)

  return {
    id: msg.id ?? '',
    threadId: msg.threadId ?? undefined,
    sender,
    senderEmail,
    subject: getHeader(headers, 'Subject') || '(no subject)',
    preview: msg.snippet ?? '',
    body: body ? body.split('\n\n').filter(Boolean) : [''],
    timestamp,
    read: !labelIds.includes('UNREAD'),
    flagged: labelIds.includes('STARRED'),
    folder: inferFolder(labelIds),
    attachments: extractAttachments(msg.payload),
    actionRequired: false,
    priority: labelIds.includes('IMPORTANT'),
  }
}

// ---------------------------------------------------------------------------
// Gmail provider implementation
// ---------------------------------------------------------------------------

const gmailProvider: EmailProvider = {
  name: 'gmail',
  displayName: 'Gmail',

  getAuthUrl(options?: AuthOptions): string {
    const oauth2Client = createOAuthClient(options?.redirectUri)
    return oauth2Client.generateAuthUrl({
      access_type: 'offline',
      prompt: 'consent', // force refresh_token to be returned
      scope: options?.scopes ?? [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.modify',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile',
      ],
      state: options?.state,
    })
  },

  async exchangeCodeForTokens(code: string, redirectUri: string): Promise<AuthTokens> {
    const oauth2Client = createOAuthClient(redirectUri)
    const { tokens } = await oauth2Client.getToken(code)

    // Fetch user email for display
    oauth2Client.setCredentials(tokens)
    const oauth2 = google.oauth2({ version: 'v2', auth: oauth2Client })
    const { data } = await oauth2.userinfo.get()

    return {
      provider: 'gmail',
      accessToken: tokens.access_token!,
      refreshToken: tokens.refresh_token ?? undefined,
      expiresAt: tokens.expiry_date ?? undefined,
      userEmail: data.email ?? undefined,
      scope: tokens.scope ?? undefined,
    }
  },

  async refreshTokens(tokens: AuthTokens): Promise<AuthTokens> {
    const oauth2Client = createOAuthClient()
    oauth2Client.setCredentials({
      access_token: tokens.accessToken,
      refresh_token: tokens.refreshToken,
    })
    const { credentials } = await oauth2Client.refreshAccessToken()
    return {
      ...tokens,
      accessToken: credentials.access_token!,
      expiresAt: credentials.expiry_date ?? undefined,
    }
  },

  async isAuthenticated(tokens: AuthTokens): Promise<boolean> {
    if (!tokens.accessToken) return false
    if (tokens.expiresAt && tokens.expiresAt < Date.now()) return false
    return true
  },

  async getFolders(tokens: AuthTokens): Promise<Folder[]> {
    const oauth2Client = createOAuthClient()
    oauth2Client.setCredentials({
      access_token: tokens.accessToken,
      refresh_token: tokens.refreshToken,
    })
    const gmail = google.gmail({ version: 'v1', auth: oauth2Client })
    const { data } = await gmail.users.labels.list({ userId: 'me' })
    return (data.labels ?? []).map((label) => ({
      id: label.id ?? '',
      name: label.name ?? '',
      displayName: label.name ?? '',
      unreadCount: label.messagesUnread ?? undefined,
      count: label.messagesTotal ?? undefined,
    }))
  },

  async getEmails(
    tokens: AuthTokens,
    folder = 'inbox',
    options: QueryOptions = {}
  ): Promise<EmailMessage[]> {
    const oauth2Client = createOAuthClient()
    oauth2Client.setCredentials({
      access_token: tokens.accessToken,
      refresh_token: tokens.refreshToken,
    })
    const gmail = google.gmail({ version: 'v1', auth: oauth2Client })

    const labelIds = FOLDER_TO_LABEL[folder]
      ? [FOLDER_TO_LABEL[folder]]
      : undefined

    const listRes = await gmail.users.messages.list({
      userId: 'me',
      labelIds,
      maxResults: options.maxResults ?? 50,
      pageToken: options.pageToken,
      q: options.query,
    })

    const messageRefs = listRes.data.messages ?? []
    if (messageRefs.length === 0) return []

    // Fetch full messages in parallel (up to 10 at a time to avoid rate limits)
    const CHUNK = 10
    const messages: EmailMessage[] = []
    for (let i = 0; i < messageRefs.length; i += CHUNK) {
      const chunk = messageRefs.slice(i, i + CHUNK)
      const fetched = await Promise.all(
        chunk.map((ref) =>
          gmail.users.messages
            .get({ userId: 'me', id: ref.id!, format: 'full' })
            .then((r) => toEmailMessage(r.data))
        )
      )
      messages.push(...fetched)
    }

    return messages
  },

  async getEmail(tokens: AuthTokens, id: string): Promise<EmailMessage> {
    const oauth2Client = createOAuthClient()
    oauth2Client.setCredentials({
      access_token: tokens.accessToken,
      refresh_token: tokens.refreshToken,
    })
    const gmail = google.gmail({ version: 'v1', auth: oauth2Client })
    const { data } = await gmail.users.messages.get({
      userId: 'me',
      id,
      format: 'full',
    })
    return toEmailMessage(data)
  },

  async sendEmail(tokens: AuthTokens, email: SendEmailOptions): Promise<void> {
    const oauth2Client = createOAuthClient()
    oauth2Client.setCredentials({
      access_token: tokens.accessToken,
      refresh_token: tokens.refreshToken,
    })
    const gmail = google.gmail({ version: 'v1', auth: oauth2Client })

    const toList = Array.isArray(email.to) ? email.to.join(', ') : email.to
    const raw = [
      `To: ${toList}`,
      email.cc ? `Cc: ${Array.isArray(email.cc) ? email.cc.join(', ') : email.cc}` : '',
      email.bcc ? `Bcc: ${Array.isArray(email.bcc) ? email.bcc.join(', ') : email.bcc}` : '',
      `Subject: ${email.subject}`,
      'Content-Type: text/plain; charset=UTF-8',
      '',
      email.body,
    ]
      .filter(Boolean)
      .join('\r\n')

    const encoded = Buffer.from(raw).toString('base64url')
    await gmail.users.messages.send({
      userId: 'me',
      requestBody: {
        raw: encoded,
        threadId: email.threadId,
      },
    })
  },

  async markAsRead(tokens: AuthTokens, ids: string[]): Promise<void> {
    const oauth2Client = createOAuthClient()
    oauth2Client.setCredentials({ access_token: tokens.accessToken, refresh_token: tokens.refreshToken })
    const gmail = google.gmail({ version: 'v1', auth: oauth2Client })
    await Promise.all(
      ids.map((id) =>
        gmail.users.messages.modify({
          userId: 'me',
          id,
          requestBody: { removeLabelIds: ['UNREAD'] },
        })
      )
    )
  },

  async markAsUnread(tokens: AuthTokens, ids: string[]): Promise<void> {
    const oauth2Client = createOAuthClient()
    oauth2Client.setCredentials({ access_token: tokens.accessToken, refresh_token: tokens.refreshToken })
    const gmail = google.gmail({ version: 'v1', auth: oauth2Client })
    await Promise.all(
      ids.map((id) =>
        gmail.users.messages.modify({
          userId: 'me',
          id,
          requestBody: { addLabelIds: ['UNREAD'] },
        })
      )
    )
  },

  async archiveEmails(tokens: AuthTokens, ids: string[]): Promise<void> {
    const oauth2Client = createOAuthClient()
    oauth2Client.setCredentials({ access_token: tokens.accessToken, refresh_token: tokens.refreshToken })
    const gmail = google.gmail({ version: 'v1', auth: oauth2Client })
    await Promise.all(
      ids.map((id) =>
        gmail.users.messages.modify({
          userId: 'me',
          id,
          requestBody: { removeLabelIds: ['INBOX'] },
        })
      )
    )
  },

  async deleteEmails(tokens: AuthTokens, ids: string[]): Promise<void> {
    const oauth2Client = createOAuthClient()
    oauth2Client.setCredentials({ access_token: tokens.accessToken, refresh_token: tokens.refreshToken })
    const gmail = google.gmail({ version: 'v1', auth: oauth2Client })
    await Promise.all(
      ids.map((id) => gmail.users.messages.trash({ userId: 'me', id }))
    )
  },
}

registerProvider(gmailProvider)
export default gmailProvider

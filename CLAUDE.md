# Openfield — Architecture & Developer Guide

## What Is This?

**Fieldwork** is a calm, focused email client built on Next.js/React. The goal is an inbox experience that reduces noise and supports deep work. It is designed as a web-first app today and will eventually ship as an **Electron desktop application**.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Browser (React, "use client")                               │
│                                                              │
│  app/page.tsx                                                │
│   ├─ useAuth()     ── checks /api/auth/session               │
│   └─ useEmails()   ── fetches /api/emails                    │
│        │                                                     │
│        ▼   props                                             │
│   Existing UI components (untouched):                        │
│   FolderNav │ EmailList │ EmailViewer │ AiContextPanel …     │
└─────────────────────┬────────────────────────────────────────┘
                      │  HTTP (Next.js API routes)
┌─────────────────────▼────────────────────────────────────────┐
│  Server (Node.js / Next.js App Router)                       │
│                                                              │
│  app/api/auth/signin    ── starts OAuth flow                 │
│  app/api/auth/callback  ── exchanges code, saves session     │
│  app/api/auth/session   ── returns safe session info         │
│  app/api/auth/signout   ── destroys session                  │
│  app/api/emails         ── calls provider, returns Email[]   │
│  app/api/draft-reply    ── Claude Haiku AI draft             │
│                                                              │
│  lib/session.ts ── iron-session (AES-256, HTTP-only cookie)  │
│                                                              │
│  providers/                                                  │
│   ├─ interface.ts  ── canonical types + EmailProvider spec   │
│   ├─ gmail.ts      ── Google Gmail API adapter               │
│   └─ index.ts      ── registry / factory                     │
└──────────────────────────────────────────────────────────────┘
```

---

## Token Storage

Tokens are **never** stored in `localStorage`, `sessionStorage`, or any client-accessible location.

| Layer | What is stored | How |
|---|---|---|
| Server session cookie | Encrypted access + refresh tokens, user email | `iron-session` (AES-256, HTTP-only, SameSite=Lax) |
| Client | Session metadata only (email, provider name) | Returned safely by `/api/auth/session` |

### Electron migration path

When the app moves to Electron, replace `lib/session.ts` with a keychain-backed store (e.g. `keytar` / `electron-keytar`). The `SessionData` shape and the provider interface are unchanged — only the persistence layer swaps.

```typescript
// Electron replacement for lib/session.ts (conceptual)
import keytar from "keytar"
export async function getTokens(provider: string): Promise<TokenSet | null> {
  const raw = await keytar.getPassword("openfield", provider)
  return raw ? JSON.parse(raw) : null
}
```

---

## Provider Interface

Every email backend implements `EmailProvider` from `providers/interface.ts`. The UI and API routes are **only** aware of this interface.

```typescript
interface EmailProvider {
  readonly id: string        // "gmail", "office365", …
  readonly name: string      // "Gmail", "Microsoft 365", …
  readonly icon?: string     // path to public asset

  // OAuth lifecycle
  getAuthUrl(redirectUri: string, state?: string): string
  exchangeCode(code: string, redirectUri: string): Promise<TokenSet>
  refreshTokens(tokens: TokenSet): Promise<TokenSet>
  getUserInfo(tokens: TokenSet): Promise<AuthInfo>

  // Email operations
  listEmails(tokens: TokenSet, options?: ListEmailsOptions): Promise<Email[]>
  getEmail(tokens: TokenSet, id: string): Promise<Email>
  markAsRead(tokens: TokenSet, id: string): Promise<void>
}
```

### Email shape (canonical)

```typescript
interface Email {
  id: string
  sender: string          // display name
  senderEmail: string
  senderTitle: string     // job title (empty if unavailable)
  senderCompany: string   // domain or company name
  lastInteraction: string // "Feb 14, 2026"
  subject: string
  preview: string         // short snippet
  timestamp: string       // "2:14 PM", "Mon", "Mar 5"
  read: boolean
  flagged: boolean
  actionRequired: boolean // set by AI enrichment layer
  folder: string          // "inbox" | "sent" | "drafts" | "spam" | "trash"
  body: string[]          // full body as paragraphs
  actions: EmailAction[]  // set by AI enrichment layer
  keyDetails: KeyDetail[] // header-derived
  threadSummary: string[] // set by AI enrichment layer
  attachments: Attachment[]
  priority: boolean
  priorityReason?: string
  isDistributionList?: boolean
}
```

---

## How to Add a New Provider

Follow these four steps to add, for example, Office 365:

### Step 1 — Create `providers/office365.ts`

```typescript
import type { EmailProvider, Email, TokenSet, AuthInfo, ListEmailsOptions } from "./interface"

export class Office365Provider implements EmailProvider {
  readonly id = "office365"
  readonly name = "Microsoft 365"
  readonly icon = "/icons/microsoft.svg"

  getAuthUrl(redirectUri: string, state?: string): string {
    // Use MSAL or the Microsoft identity platform URL builder
    const params = new URLSearchParams({
      client_id: process.env.AZURE_CLIENT_ID!,
      response_type: "code",
      redirect_uri: redirectUri,
      scope: "openid email profile Mail.Read offline_access",
      state: state ?? "",
    })
    return `https://login.microsoftonline.com/common/oauth2/v2.0/authorize?${params}`
  }

  async exchangeCode(code: string, redirectUri: string): Promise<TokenSet> {
    // POST to https://login.microsoftonline.com/common/oauth2/v2.0/token
  }

  async refreshTokens(tokens: TokenSet): Promise<TokenSet> {
    // POST with grant_type=refresh_token
  }

  async getUserInfo(tokens: TokenSet): Promise<AuthInfo> {
    // GET https://graph.microsoft.com/v1.0/me
  }

  async listEmails(tokens: TokenSet, options?: ListEmailsOptions): Promise<Email[]> {
    // GET https://graph.microsoft.com/v1.0/me/messages
    // Map Microsoft Graph Message → Email
  }

  async getEmail(tokens: TokenSet, id: string): Promise<Email> {
    // GET https://graph.microsoft.com/v1.0/me/messages/{id}
  }

  async markAsRead(tokens: TokenSet, id: string): Promise<void> {
    // PATCH https://graph.microsoft.com/v1.0/me/messages/{id}
    // body: { isRead: true }
  }
}
```

### Step 2 — Register in `providers/index.ts`

```typescript
import { Office365Provider } from "./office365"

const PROVIDERS: Record<string, EmailProvider> = {
  gmail: new GmailProvider(),
  office365: new Office365Provider(),   // ← add this line
}
```

### Step 3 — Add OAuth credentials to `.env.local`

```
AZURE_CLIENT_ID=your_azure_app_id
AZURE_CLIENT_SECRET=your_azure_secret
```

### Step 4 — Add a sign-in button in `components/sign-in.tsx`

```tsx
<a href="/api/auth/signin?provider=office365" …>
  Sign in with Microsoft
</a>
```

That's everything. The auth routes, email API, and all UI components automatically support the new provider because they go through the registry and the canonical `Email` interface.

---

## Key Files Reference

| File | Purpose |
|---|---|
| `providers/interface.ts` | Canonical `Email` type + `EmailProvider` contract |
| `providers/gmail.ts` | Gmail OAuth + Gmail API adapter |
| `providers/index.ts` | Provider registry (`getProvider`, `listProviders`) |
| `lib/session.ts` | Encrypted HTTP-only session (iron-session) |
| `app/api/auth/signin/route.ts` | Initiates OAuth redirect |
| `app/api/auth/callback/route.ts` | Handles code exchange + session write |
| `app/api/auth/session/route.ts` | Exposes safe session state to client |
| `app/api/auth/signout/route.ts` | Destroys session |
| `app/api/emails/route.ts` | Lists emails; handles token refresh |
| `app/api/draft-reply/route.ts` | Claude Haiku AI reply drafts |
| `hooks/use-auth.ts` | Client hook: auth state + signOut() |
| `hooks/use-emails.ts` | Client hook: fetches + caches Email[] |
| `components/sign-in.tsx` | Authentication gate screen |
| `app/page.tsx` | Main orchestration (thin: auth → emails → UI) |

---

## Development Setup

```bash
# 1. Clone & install
git clone https://github.com/davidjrothstein/openfield
cd openfield
npm install

# 2. Configure environment
cp .env.example .env.local
# Edit .env.local with your credentials

# 3. Run
npm run dev
```

### Google Cloud Console checklist

1. Create a project at https://console.cloud.google.com/
2. Enable the **Gmail API**
3. Create **OAuth 2.0 credentials** (Web application)
4. Add authorized redirect URI: `http://localhost:3000/api/auth/callback`
5. Copy Client ID → `GOOGLE_CLIENT_ID`
6. Copy Client Secret → `GOOGLE_CLIENT_SECRET`

---

## Design Principles

- **UI components are never modified** for provider-specific concerns. All email data arrives as the canonical `Email` type via hooks.
- **The server is the trust boundary.** Tokens only live in encrypted server-side cookies. API routes validate auth on every request.
- **Providers are stateless.** The same `GmailProvider` instance handles all users; per-user tokens are passed as arguments.
- **Token refresh is transparent.** `/api/emails` checks expiry before each call and silently refreshes, updating the session with fresh tokens.
- **Electron-ready.** The provider layer has no HTTP/cookie coupling. Swapping `lib/session.ts` for a keychain store is the only change needed for desktop deployment.

# OpenField — Architecture Reference

A calm, focused AI email client. Web-first, Electron-additive, provider-agnostic.

---

## Project structure

```
openfield/
├── app/                        Next.js App Router
│   ├── api/
│   │   ├── auth/
│   │   │   ├── gmail/route.ts  Initiate Gmail OAuth flow
│   │   │   ├── callback/route.ts  OAuth callback (token exchange)
│   │   │   ├── status/route.ts    Check auth state
│   │   │   └── logout/route.ts    Clear session cookie
│   │   ├── draft-reply/route.ts   AI reply generation (Claude Haiku)
│   │   └── emails/route.ts        Fetch emails from active provider
│   ├── layout.tsx
│   ├── page.tsx                Main email client shell
│   └── globals.css
├── components/                 UI components (untouched from v0)
│   └── ui/                     shadcn/ui primitives
├── electron/
│   ├── main.js                 Electron main process
│   └── preload.js              Secure renderer bridge
├── hooks/                      React hooks
├── lib/
│   ├── email-data.ts           Static demo email dataset
│   ├── token-storage.ts        AES-256-GCM cookie encryption
│   └── utils.ts
├── providers/
│   ├── index.ts                EmailProvider interface + registry
│   ├── gmail.ts                Gmail implementation
│   └── mock.ts                 Static demo provider (fallback)
├── public/
├── CLAUDE.md                   This file
├── .env.example
└── package.json
```

---

## Email provider interface

All providers live in `providers/` and must implement `EmailProvider` from
`providers/index.ts`. The interface is the single contract between the rest of
the application and any email backend.

```typescript
interface EmailProvider {
  readonly name: string          // machine id, e.g. "gmail"
  readonly displayName: string   // shown in UI, e.g. "Gmail"

  // Auth
  getAuthUrl(options?: AuthOptions): string
  exchangeCodeForTokens(code: string, redirectUri: string): Promise<AuthTokens>
  refreshTokens(tokens: AuthTokens): Promise<AuthTokens>
  isAuthenticated(tokens: AuthTokens): Promise<boolean>

  // Read
  getFolders(tokens: AuthTokens): Promise<Folder[]>
  getEmails(tokens: AuthTokens, folder?: string, options?: QueryOptions): Promise<EmailMessage[]>
  getEmail(tokens: AuthTokens, id: string): Promise<EmailMessage>

  // Write
  sendEmail(tokens: AuthTokens, email: SendEmailOptions): Promise<void>
  markAsRead(tokens: AuthTokens, ids: string[]): Promise<void>
  markAsUnread(tokens: AuthTokens, ids: string[]): Promise<void>
  archiveEmails(tokens: AuthTokens, ids: string[]): Promise<void>
  deleteEmails(tokens: AuthTokens, ids: string[]): Promise<void>
}
```

### Token shape

```typescript
interface AuthTokens {
  provider: string        // must match EmailProvider.name
  accessToken: string
  refreshToken?: string
  expiresAt?: number      // Unix ms timestamp
  userEmail?: string
  scope?: string
}
```

Tokens are **never** stored in localStorage. They are AES-256-GCM encrypted
and persisted in an HTTP-only cookie (`openfield_session`) by
`lib/token-storage.ts`. The cookie is inaccessible to client-side JavaScript.

---

## Adding a new provider

**Step 1 — Create `providers/<name>.ts`**

```typescript
import { EmailProvider, AuthTokens, EmailMessage, /* ... */ registerProvider } from './index'

const myProvider: EmailProvider = {
  name: 'office365',           // unique, lowercase, no spaces
  displayName: 'Office 365',

  getAuthUrl(options) {
    // Return the Microsoft identity platform OAuth URL
    return `https://login.microsoftonline.com/common/oauth2/v2.0/authorize?...`
  },

  async exchangeCodeForTokens(code, redirectUri) {
    // Exchange code → tokens via Microsoft token endpoint
    return { provider: 'office365', accessToken: '...', refreshToken: '...' }
  },

  async refreshTokens(tokens) { /* refresh via MSAL */ return tokens },
  async isAuthenticated(tokens) { return !!tokens.accessToken },
  async getFolders(tokens) { /* call MS Graph /me/mailFolders */ return [] },
  async getEmails(tokens, folder, options) { /* MS Graph /me/messages */ return [] },
  async getEmail(tokens, id) { /* MS Graph /me/messages/:id */ throw new Error() },
  async sendEmail(tokens, email) { /* MS Graph /me/sendMail */ },
  async markAsRead(tokens, ids) {},
  async markAsUnread(tokens, ids) {},
  async archiveEmails(tokens, ids) {},
  async deleteEmails(tokens, ids) {},
}

registerProvider(myProvider)
export default myProvider
```

**Step 2 — Register it in `providers/index.ts`**

Add one import line at the bottom of `providers/index.ts`:

```typescript
import './office365'
```

**Step 3 — Add an OAuth route (if needed)**

Copy `app/api/auth/gmail/route.ts` → `app/api/auth/office365/route.ts` and
swap `getProvider('gmail')` for `getProvider('office365')`.

**Step 4 — Add required env vars to `.env.local` and `.env.example`**

That's it. No core logic changes required.

---

## Token storage

`lib/token-storage.ts` provides four functions:

| Function | Description |
|---|---|
| `getStoredTokens()` | Read + decrypt tokens from the session cookie |
| `storeTokens(tokens)` | Encrypt + write tokens to the session cookie |
| `clearTokens()` | Delete the session cookie (logout) |
| `encryptTokens(tokens)` | Low-level: encrypt to string |
| `decryptTokens(str)` | Low-level: decrypt from string |

The encryption key is `OPENFIELD_TOKEN_SECRET` (env var). Must be set in
production. Generate one with:

```bash
openssl rand -hex 32
```

---

## Electron

The Electron wrapper in `electron/` is purely additive — the web app runs
identically in a browser and in Electron.

### Development

```bash
npm run electron:dev
# Starts next dev + waits for :3000 + opens Electron window
```

### Production build

```bash
npm run electron:build
# next build → electron-builder → dist/
```

### Platform detection

The preload script exposes `window.electron.isElectron` (boolean) and
`window.electron.platform` (string) to the renderer. Use these sparingly for
platform-specific UI tweaks (e.g. traffic-light button spacing on macOS).

The title bar uses `titleBarStyle: 'hiddenInset'` on macOS so the native
traffic-light buttons overlay the drag region defined by the `.app-drag-region`
CSS class already present in the UI.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `OPENFIELD_TOKEN_SECRET` | Yes (production) | 32-byte AES encryption key |
| `GOOGLE_CLIENT_ID` | Yes (Gmail) | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Yes (Gmail) | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | No | Defaults to `$NEXT_PUBLIC_APP_URL/api/auth/callback` |
| `NEXT_PUBLIC_APP_URL` | No | Base URL, defaults to `http://localhost:3000` |

See `.env.example` for a full template.

---

## Gmail OAuth setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials
2. Create an OAuth 2.0 Client ID (Web application)
3. Add `http://localhost:3000/api/auth/callback` as an Authorized Redirect URI
4. Copy the client ID and secret into `.env.local`
5. Enable the **Gmail API** in APIs & Services → Library
6. Visit `http://localhost:3000/api/auth/gmail` to trigger the OAuth flow

---

## Scripts

| Script | Description |
|---|---|
| `npm run dev` | Next.js dev server |
| `npm run build` | Production Next.js build |
| `npm run start` | Serve the production build |
| `npm run electron:dev` | Dev mode with Electron window |
| `npm run electron:build` | Build distributable Electron app |
| `npm run electron:pack` | Package without creating installer |
| `npm run lint` | ESLint |

---

## UI architecture

The UI shell in `app/page.tsx` + `components/` is intentionally left intact
from its v0 origins. All new functionality wraps around it:

- **Data**: `emailList` state (in `page.tsx`) is populated by `/api/emails`.
  Falls back to static demo data from `lib/email-data.ts` when unauthenticated.
- **Auth**: The title bar shows a "Connect Gmail" link (unauthenticated) or the
  connected account email + sign-out button (authenticated).
- **Components**: `components/email-list.tsx`, `components/email-viewer.tsx`,
  etc. receive `emailList` data via existing props — no internal changes needed.

The flow is:
```
User → /api/auth/gmail → Google OAuth → /api/auth/callback
     → token encrypted → HTTP-only cookie
     → /api/emails → GmailProvider.getEmails() → UI
```

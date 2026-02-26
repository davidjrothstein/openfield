/**
 * Secure server-side session via iron-session.
 *
 * Tokens are encrypted using AES-256-CBC (iron-session default) and stored in
 * an HTTP-only, SameSite=Lax cookie — they never appear in JavaScript or
 * localStorage.
 *
 * Electron note: When this application moves to Electron, replace this module
 * with a keychain-backed store (e.g. `keytar`) while keeping the same
 * SessionData shape. The provider layer is agnostic to where tokens are stored.
 */

import { getIronSession, type IronSession } from "iron-session"
import { cookies } from "next/headers"
import type { TokenSet } from "@/providers/interface"

// ---------------------------------------------------------------------------
// Session shape
// ---------------------------------------------------------------------------

export interface SessionData {
  /** Provider ID, e.g. "gmail" */
  provider?: string
  /** Encrypted OAuth tokens — never exposed to the client */
  tokens?: TokenSet
  /** Authenticated user's email address */
  userEmail?: string
  /** Authenticated user's display name */
  userName?: string
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const SESSION_COOKIE = "openfield-session"

/** SESSION_SECRET must be at least 32 characters. Set in .env.local. */
function getSessionOptions() {
  const password = process.env.SESSION_SECRET
  if (!password || password.length < 32) {
    throw new Error(
      "SESSION_SECRET env var is missing or too short (minimum 32 characters). " +
        "Generate one with: openssl rand -hex 32",
    )
  }
  return {
    password,
    cookieName: SESSION_COOKIE,
    cookieOptions: {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax" as const,
      // 30-day sliding expiry
      maxAge: 60 * 60 * 24 * 30,
    },
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function getSession(): Promise<IronSession<SessionData>> {
  return getIronSession<SessionData>(await cookies(), getSessionOptions())
}

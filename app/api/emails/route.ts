/**
 * GET /api/emails?folder=inbox&maxResults=25
 *
 * Fetches emails from the authenticated user's provider.
 * Handles token refresh transparently — if the access token is expired the
 * session is updated with fresh tokens before the request proceeds.
 *
 * Query parameters:
 *   folder      — inbox | sent | drafts | spam | trash (default: inbox)
 *   maxResults  — number of emails to return (default: 25, max: 50)
 *   query       — provider-native search string (optional)
 *
 * Returns: Email[] (matches the shape in providers/interface.ts)
 */

import { NextResponse } from "next/server"
import { getProvider } from "@/providers"
import { getSession } from "@/lib/session"
import type { TokenSet } from "@/providers/interface"

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)

  // ------------------------------------------------------------------
  // Auth check
  // ------------------------------------------------------------------
  const session = await getSession()
  if (!session.tokens?.access_token || !session.provider) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 })
  }

  const provider = getProvider(session.provider)
  if (!provider) {
    return NextResponse.json({ error: "Unknown provider in session" }, { status: 500 })
  }

  // ------------------------------------------------------------------
  // Token refresh if expired
  // ------------------------------------------------------------------
  let tokens: TokenSet = session.tokens
  const isExpired =
    tokens.expiry_date != null && Date.now() >= tokens.expiry_date - 60_000 // 60s buffer

  if (isExpired && tokens.refresh_token) {
    try {
      tokens = await provider.refreshTokens(tokens)
      session.tokens = tokens
      await session.save()
    } catch (err) {
      console.error("[api/emails] token refresh failed:", err)
      return NextResponse.json({ error: "Token refresh failed" }, { status: 401 })
    }
  }

  // ------------------------------------------------------------------
  // Parse & validate query params
  // ------------------------------------------------------------------
  const folder = searchParams.get("folder") ?? "inbox"
  const maxResults = Math.min(
    parseInt(searchParams.get("maxResults") ?? "25", 10) || 25,
    50,
  )
  const query = searchParams.get("query") ?? undefined

  // ------------------------------------------------------------------
  // Fetch from provider
  // ------------------------------------------------------------------
  try {
    const emails = await provider.listEmails(tokens, { folder, maxResults, query })
    return NextResponse.json(emails)
  } catch (err) {
    console.error("[api/emails] listEmails failed:", err)
    return NextResponse.json({ error: "Failed to fetch emails" }, { status: 500 })
  }
}

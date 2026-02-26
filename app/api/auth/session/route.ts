/**
 * GET /api/auth/session
 *
 * Returns the current authentication state to client-side code.
 * Deliberately exposes only safe fields — tokens are never included.
 *
 * Response shape:
 *   { authenticated: false }
 *   { authenticated: true, provider: "gmail", userEmail: "...", userName: "..." }
 */

import { NextResponse } from "next/server"
import { getSession } from "@/lib/session"

export async function GET() {
  const session = await getSession()

  if (!session.tokens?.access_token) {
    return NextResponse.json({ authenticated: false })
  }

  return NextResponse.json({
    authenticated: true,
    provider: session.provider,
    userEmail: session.userEmail,
    userName: session.userName,
  })
}

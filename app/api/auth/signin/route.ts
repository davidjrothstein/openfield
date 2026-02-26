/**
 * GET /api/auth/signin?provider=gmail
 *
 * Redirects the user to the provider's OAuth authorization page.
 * The provider ID is encoded into the OAuth `state` parameter so the callback
 * knows which provider to use without requiring a separate cookie.
 */

import { NextResponse } from "next/server"
import { getProvider } from "@/providers"

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const providerId = searchParams.get("provider") ?? "gmail"

  const provider = getProvider(providerId)
  if (!provider) {
    return NextResponse.json({ error: `Unknown provider: ${providerId}` }, { status: 400 })
  }

  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL ?? new URL(request.url).origin
  const redirectUri = `${baseUrl}/api/auth/callback`

  // Encode provider ID as the state so the callback can look it up
  const authUrl = provider.getAuthUrl(redirectUri, providerId)

  return NextResponse.redirect(authUrl)
}

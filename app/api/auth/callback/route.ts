/**
 * GET /api/auth/callback?code=...&state=<providerId>
 *
 * Handles the OAuth redirect from the identity provider:
 *   1. Exchanges the authorization code for tokens
 *   2. Fetches the user's profile
 *   3. Stores everything in an encrypted HTTP-only session cookie
 *   4. Redirects to the application home page
 *
 * On error, redirects to /?error=<reason> so the UI can show a message.
 */

import { NextResponse } from "next/server"
import { getProvider } from "@/providers"
import { getSession } from "@/lib/session"

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL ?? origin

  const code = searchParams.get("code")
  const state = searchParams.get("state") // provider ID
  const error = searchParams.get("error")

  // User denied access or something went wrong on the provider side
  if (error || !code) {
    const reason = error ?? "missing_code"
    return NextResponse.redirect(`${baseUrl}/?error=${encodeURIComponent(reason)}`)
  }

  const providerId = state ?? "gmail"
  const provider = getProvider(providerId)
  if (!provider) {
    return NextResponse.redirect(`${baseUrl}/?error=unknown_provider`)
  }

  try {
    const redirectUri = `${baseUrl}/api/auth/callback`
    const tokens = await provider.exchangeCode(code, redirectUri)
    const userInfo = await provider.getUserInfo(tokens)

    const session = await getSession()
    session.provider = providerId
    session.tokens = tokens
    session.userEmail = userInfo.userEmail
    session.userName = userInfo.userName
    await session.save()

    return NextResponse.redirect(`${baseUrl}/`)
  } catch (err) {
    console.error("[auth/callback] token exchange failed:", err)
    return NextResponse.redirect(`${baseUrl}/?error=token_exchange_failed`)
  }
}

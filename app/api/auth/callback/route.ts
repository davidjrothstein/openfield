/**
 * GET /api/auth/callback
 *
 * OAuth 2.0 callback handler. Google redirects here after the user grants
 * (or denies) permission. On success we exchange the authorization code for
 * tokens, encrypt them, and store them in an HTTP-only cookie before
 * redirecting back to the app.
 */

import { NextResponse } from 'next/server'
import { getProvider } from '@/providers/index'
import { storeTokens } from '@/lib/token-storage'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const code = searchParams.get('code')
  const state = searchParams.get('state') // encoded redirectAfter
  const error = searchParams.get('error')

  const appUrl =
    process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000'
  const redirectAfter = state ? decodeURIComponent(state) : '/'

  // User denied access
  if (error) {
    console.warn('[auth/callback] OAuth error:', error)
    return NextResponse.redirect(
      `${appUrl}/?auth_error=${encodeURIComponent(error)}`
    )
  }

  if (!code) {
    return NextResponse.redirect(
      `${appUrl}/?auth_error=missing_code`
    )
  }

  try {
    const provider = getProvider('gmail')
    const redirectUri =
      process.env.GOOGLE_REDIRECT_URI ??
      `${appUrl}/api/auth/callback`

    const tokens = await provider.exchangeCodeForTokens(code, redirectUri)
    await storeTokens(tokens)

    return NextResponse.redirect(`${appUrl}${redirectAfter}`)
  } catch (err) {
    console.error('[auth/callback] Token exchange failed:', err)
    return NextResponse.redirect(
      `${appUrl}/?auth_error=token_exchange_failed`
    )
  }
}

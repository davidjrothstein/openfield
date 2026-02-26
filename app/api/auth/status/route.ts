/**
 * GET /api/auth/status
 *
 * Returns the current authentication status and the connected provider/email.
 * Used by the client to decide whether to show the Gmail connect button.
 *
 * Response shape:
 *   { authenticated: false }
 *   { authenticated: true, provider: "gmail", userEmail: "user@gmail.com" }
 */

import { NextResponse } from 'next/server'
import { getStoredTokens } from '@/lib/token-storage'
import { getProvider } from '@/providers/index'

export async function GET() {
  try {
    const tokens = await getStoredTokens()
    if (!tokens) {
      return NextResponse.json({ authenticated: false })
    }

    const provider = getProvider(tokens.provider)
    const valid = await provider.isAuthenticated(tokens)

    if (!valid) {
      // Attempt a silent token refresh
      try {
        await provider.refreshTokens(tokens)
        return NextResponse.json({
          authenticated: true,
          provider: tokens.provider,
          userEmail: tokens.userEmail,
        })
      } catch {
        return NextResponse.json({ authenticated: false })
      }
    }

    return NextResponse.json({
      authenticated: true,
      provider: tokens.provider,
      userEmail: tokens.userEmail,
    })
  } catch (err) {
    console.error('[auth/status]', err)
    return NextResponse.json({ authenticated: false })
  }
}

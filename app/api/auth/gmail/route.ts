/**
 * GET /api/auth/gmail
 *
 * Initiates the Gmail OAuth 2.0 flow by redirecting the user to Google's
 * authorization page. On success, Google redirects back to /api/auth/callback.
 */

import { NextResponse } from 'next/server'
import { getProvider } from '@/providers/index'

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const redirectAfter = searchParams.get('redirectAfter') ?? '/'

    const provider = getProvider('gmail')
    const redirectUri =
      process.env.GOOGLE_REDIRECT_URI ??
      `${process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000'}/api/auth/callback`

    const authUrl = provider.getAuthUrl({
      redirectUri,
      // Pass the post-auth destination through OAuth state
      state: encodeURIComponent(redirectAfter),
    })

    return NextResponse.redirect(authUrl)
  } catch (err) {
    console.error('[auth/gmail] Failed to build auth URL:', err)
    return NextResponse.json(
      { error: 'Failed to initiate Gmail OAuth flow' },
      { status: 500 }
    )
  }
}

/**
 * GET /api/emails?folder=inbox&maxResults=50
 *
 * Returns emails from the authenticated provider (Gmail) or falls back to
 * the mock provider when no session is present. The response shape is
 * identical to the EmailMessage[] used by the UI components.
 *
 * Query parameters:
 *   folder      — folder key (inbox, sent, drafts, priority, etc.)  default: inbox
 *   maxResults  — max emails to return                               default: 50
 *   query       — provider-native search query (e.g. Gmail q param)
 *   pageToken   — pagination cursor from a previous response
 */

import { NextRequest, NextResponse } from 'next/server'
import { getStoredTokens, storeTokens } from '@/lib/token-storage'
import { getProvider } from '@/providers/index'
import type { AuthTokens } from '@/providers/index'

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl
  const folder = searchParams.get('folder') ?? 'inbox'
  const maxResults = Math.min(Number(searchParams.get('maxResults') ?? 50), 200)
  const query = searchParams.get('query') ?? undefined
  const pageToken = searchParams.get('pageToken') ?? undefined

  try {
    let tokens: AuthTokens | null = await getStoredTokens()
    let providerName = 'mock'

    if (tokens) {
      providerName = tokens.provider
      const provider = getProvider(providerName)

      // Silently refresh expired tokens
      if (tokens.expiresAt && tokens.expiresAt < Date.now()) {
        try {
          tokens = await provider.refreshTokens(tokens)
          await storeTokens(tokens)
        } catch {
          // Refresh failed — fall back to mock
          tokens = null
          providerName = 'mock'
        }
      }
    }

    const provider = getProvider(providerName)
    const finalTokens: AuthTokens = tokens ?? {
      provider: 'mock',
      accessToken: 'mock',
    }

    const emails = await provider.getEmails(finalTokens, folder, {
      maxResults,
      query,
      pageToken,
    })

    return NextResponse.json({ emails, provider: providerName })
  } catch (err) {
    console.error('[api/emails]', err)
    return NextResponse.json(
      { error: 'Failed to fetch emails' },
      { status: 500 }
    )
  }
}

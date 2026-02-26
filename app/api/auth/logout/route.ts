/**
 * POST /api/auth/logout
 *
 * Clears the session cookie, signing the user out of their email provider.
 */

import { NextResponse } from 'next/server'
import { clearTokens } from '@/lib/token-storage'

export async function POST() {
  try {
    await clearTokens()
    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error('[auth/logout]', err)
    return NextResponse.json({ error: 'Logout failed' }, { status: 500 })
  }
}

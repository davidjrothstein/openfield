/**
 * POST /api/auth/signout
 *
 * Destroys the session cookie and redirects to the home page.
 * Uses POST to avoid CSRF via link-prefetching.
 */

import { NextResponse } from "next/server"
import { getSession } from "@/lib/session"

export async function POST(request: Request) {
  const { origin } = new URL(request.url)
  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL ?? origin

  const session = await getSession()
  session.destroy()

  return NextResponse.redirect(`${baseUrl}/`)
}

"use client"

import { useState, useEffect } from "react"

/**
 * SignIn — full-screen authentication gate.
 *
 * Shown when the user has no active session. Clicking the Gmail button
 * navigates to /api/auth/signin?provider=gmail which starts the OAuth flow.
 *
 * Reads the optional ?error= query param client-side to avoid requiring a
 * Suspense boundary for useSearchParams.
 *
 * No existing UI components are modified; this is an additive wrapper.
 */

const ERROR_MESSAGES: Record<string, string> = {
  access_denied: "Access was denied. Please try again.",
  token_exchange_failed: "Something went wrong during sign-in. Please try again.",
  auth_failed: "Authentication failed. Please try again.",
}

export function SignIn() {
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const err = params.get("error")
    if (err) {
      setErrorMessage(ERROR_MESSAGES[err] ?? "An error occurred. Please try again.")
    }
  }, [])

  return (
    <div className="flex h-screen w-screen flex-col items-center justify-center bg-background text-foreground">
      {/* App wordmark */}
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Fieldwork</h1>
        <p className="mt-1 text-sm text-muted-foreground">Your calm email client</p>
      </div>

      {/* Sign-in card */}
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-8 shadow-sm">
        <h2 className="mb-1 text-base font-medium">Connect your inbox</h2>
        <p className="mb-6 text-sm text-muted-foreground">
          Sign in to start reading your real emails. Tokens are stored securely
          server-side and never exposed to the browser.
        </p>

        {errorMessage && (
          <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {errorMessage}
          </div>
        )}

        <a
          href="/api/auth/signin?provider=gmail"
          className="flex w-full items-center justify-center gap-3 rounded-lg border border-border bg-background px-4 py-2.5 text-sm font-medium transition-colors hover:bg-muted"
        >
          {/* Google "G" logo */}
          <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              fill="#4285F4"
            />
            <path
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              fill="#34A853"
            />
            <path
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              fill="#FBBC05"
            />
            <path
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              fill="#EA4335"
            />
          </svg>
          Sign in with Gmail
        </a>

        {/* Future providers placeholder */}
        <p className="mt-6 text-center text-[11px] text-muted-foreground/60">
          Office 365 and Exchange coming soon
        </p>
      </div>

      <p className="mt-6 max-w-xs text-center text-[11px] text-muted-foreground/50">
        Fieldwork requests read-only Gmail access. Your credentials are encrypted
        and never stored in plaintext.
      </p>
    </div>
  )
}

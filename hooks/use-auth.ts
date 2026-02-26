"use client"

/**
 * useAuth — client-side authentication state hook.
 *
 * Fetches the session from /api/auth/session on mount and exposes:
 *   - isLoading       — true until the first response arrives
 *   - isAuthenticated — false if not signed in
 *   - provider        — e.g. "gmail"
 *   - userEmail / userName — profile info
 *   - signOut()       — posts to /api/auth/signout and reloads
 */

import { useState, useEffect, useCallback } from "react"

export interface AuthState {
  isLoading: boolean
  isAuthenticated: boolean
  provider?: string
  userEmail?: string
  userName?: string
}

export function useAuth(): AuthState & { signOut: () => Promise<void> } {
  const [state, setState] = useState<AuthState>({
    isLoading: true,
    isAuthenticated: false,
  })

  useEffect(() => {
    let cancelled = false

    fetch("/api/auth/session")
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return
        setState({
          isLoading: false,
          isAuthenticated: data.authenticated === true,
          provider: data.provider,
          userEmail: data.userEmail,
          userName: data.userName,
        })
      })
      .catch(() => {
        if (!cancelled) {
          setState({ isLoading: false, isAuthenticated: false })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  const signOut = useCallback(async () => {
    await fetch("/api/auth/signout", { method: "POST" })
    // Full page reload so all client state is cleared
    window.location.href = "/"
  }, [])

  return { ...state, signOut }
}

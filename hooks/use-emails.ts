"use client"

/**
 * useEmails — fetches real emails from the authenticated provider.
 *
 * Re-fetches automatically when the folder changes.
 * Falls back to an empty array on error so the UI degrades gracefully.
 *
 * Usage:
 *   const { emails, isLoading, error, refetch } = useEmails("inbox")
 */

import { useState, useEffect, useCallback } from "react"
import type { Email } from "@/providers/interface"

interface UseEmailsResult {
  emails: Email[]
  isLoading: boolean
  error: string | null
  refetch: () => void
}

export function useEmails(folder: string = "inbox", enabled: boolean = true): UseEmailsResult {
  const [emails, setEmails] = useState<Email[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  const refetch = useCallback(() => setTick((n) => n + 1), [])

  useEffect(() => {
    if (!enabled) {
      setIsLoading(false)
      return
    }

    let cancelled = false
    setIsLoading(true)
    setError(null)

    const params = new URLSearchParams({ folder, maxResults: "25" })

    fetch(`/api/emails?${params}`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body.error ?? `HTTP ${res.status}`)
        }
        return res.json() as Promise<Email[]>
      })
      .then((data) => {
        if (cancelled) return
        setEmails(data)
        setIsLoading(false)
      })
      .catch((err: Error) => {
        if (cancelled) return
        console.error("[useEmails]", err)
        setError(err.message)
        setEmails([])
        setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [folder, tick, enabled])

  return { emails, isLoading, error, refetch }
}

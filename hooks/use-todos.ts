"use client"

import { useState, useMemo, useCallback } from "react"
import type { Email } from "@/lib/email-data"

export interface Todo {
  id: string
  text: string
  completed: boolean
  source: "manual" | "smart"
  emailId?: string
  emailActionId?: string
  emailSender?: string
  createdAt: number
}

/**
 * Smart todo deduplication rules:
 * 1. Only pull from non-distribution-list emails
 * 2. Only pull actions typed as "todo"
 * 3. If a manual todo text closely matches a smart todo, squash the smart one
 * 4. If a user completes a manual todo, suppress matching smart todos
 */
function normalizeText(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9\s]/g, "").replace(/\s+/g, " ").trim()
}

function textsMatch(a: string, b: string): boolean {
  const na = normalizeText(a)
  const nb = normalizeText(b)
  // Exact match
  if (na === nb) return true
  // One contains the other (for partial matches)
  if (na.length > 10 && nb.length > 10) {
    if (na.includes(nb) || nb.includes(na)) return true
  }
  // Word overlap -- if 60%+ of words match, consider them the same
  const wordsA = new Set(na.split(" "))
  const wordsB = new Set(nb.split(" "))
  const intersection = [...wordsA].filter((w) => wordsB.has(w))
  const overlap = intersection.length / Math.min(wordsA.size, wordsB.size)
  return overlap >= 0.6
}

export function useTodos(emails: Email[]) {
  const [manualTodos, setManualTodos] = useState<Todo[]>([])
  const [dismissedSmartIds, setDismissedSmartIds] = useState<Set<string>>(new Set())

  // Derive smart todos from all emails
  const rawSmartTodos: Todo[] = useMemo(() => {
    return emails
      .filter((e) => !e.isDistributionList)
      .flatMap((e) =>
        e.actions
          .filter((a) => a.type === "todo")
          .map((a) => ({
            id: `smart-${e.id}-${a.id}`,
            text: a.text,
            completed: false,
            source: "smart" as const,
            emailId: e.id,
            emailActionId: a.id,
            emailSender: e.sender,
            createdAt: Date.now(),
          }))
      )
  }, [emails])

  // Apply deduplication and squashing
  const smartTodos = useMemo(() => {
    return rawSmartTodos.filter((smartTodo) => {
      // Skip dismissed
      if (dismissedSmartIds.has(smartTodo.id)) return false
      // Check if any manual todo matches (including completed ones -- completed = suppress)
      const hasManualMatch = manualTodos.some((m) => textsMatch(m.text, smartTodo.text))
      return !hasManualMatch
    })
  }, [rawSmartTodos, manualTodos, dismissedSmartIds])

  const addManualTodo = useCallback((text: string) => {
    const newTodo: Todo = {
      id: `manual-${Date.now()}`,
      text,
      completed: false,
      source: "manual",
      createdAt: Date.now(),
    }
    setManualTodos((prev) => [newTodo, ...prev])
  }, [])

  const toggleTodo = useCallback((id: string) => {
    setManualTodos((prev) =>
      prev.map((t) => (t.id === id ? { ...t, completed: !t.completed } : t))
    )
  }, [])

  const removeTodo = useCallback((id: string) => {
    setManualTodos((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const acceptSmartTodo = useCallback((smartTodo: Todo) => {
    // Convert to manual so user owns it
    const manual: Todo = {
      ...smartTodo,
      id: `manual-${Date.now()}`,
      source: "manual",
      createdAt: Date.now(),
    }
    setManualTodos((prev) => [manual, ...prev])
    // Dismiss the smart version
    setDismissedSmartIds((prev) => new Set(prev).add(smartTodo.id))
  }, [])

  const dismissSmartTodo = useCallback((id: string) => {
    setDismissedSmartIds((prev) => new Set(prev).add(id))
  }, [])

  const pendingManual = manualTodos.filter((t) => !t.completed)
  const completedManual = manualTodos.filter((t) => t.completed)

  // Build dismissed list for display
  const dismissedTodos = useMemo(() => {
    return rawSmartTodos.filter((t) => dismissedSmartIds.has(t.id))
  }, [rawSmartTodos, dismissedSmartIds])

  const undismissSmartTodo = useCallback((id: string) => {
    setDismissedSmartIds((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
  }, [])

  return {
    manualTodos: pendingManual,
    completedTodos: completedManual,
    smartTodos,
    dismissedTodos,
    addManualTodo,
    toggleTodo,
    removeTodo,
    acceptSmartTodo,
    dismissSmartTodo,
    undismissSmartTodo,
    totalPending: pendingManual.length + smartTodos.length,
  }
}

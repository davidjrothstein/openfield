"use client"

import { useState, useEffect, useCallback } from "react"
import { cn } from "@/lib/utils"
import { X } from "lucide-react"

export interface SavedFilter {
  id: string
  name: string
  query: string
  conditions: FilterCondition[]
}

export interface FilterCondition {
  field: string
  value: string
  label: string
}

const PRESETS = [
  { label: "Unread", query: "unread" },
  { label: "Unread from internal senders", query: "unread from internal senders" },
  { label: "All from internal senders", query: "from internal senders" },
  { label: "Has attachments", query: "has attachments" },
  { label: "Action required", query: "action required" },
  { label: "Flagged", query: "flagged" },
]

function parseQuery(query: string): FilterCondition[] {
  const q = query.toLowerCase().trim()
  if (!q) return []
  const conditions: FilterCondition[] = []

  if (q.includes("unread")) {
    conditions.push({ field: "status", value: "unread", label: "status: unread" })
  }
  if (q.includes("read") && !q.includes("unread")) {
    conditions.push({ field: "status", value: "read", label: "status: read" })
  }
  if (q.includes("internal sender") || q.includes("internal senders")) {
    conditions.push({ field: "sender", value: "internal", label: "sender: internal" })
  }
  if (q.includes("has attachment") || q.includes("has attachments")) {
    conditions.push({ field: "attachments", value: "yes", label: "attachments: yes" })
  }
  if (q.includes("action required")) {
    conditions.push({ field: "action", value: "required", label: "action: required" })
  }
  if (q.includes("flagged")) {
    conditions.push({ field: "flagged", value: "yes", label: "flagged: yes" })
  }
  if (q.includes("priority")) {
    conditions.push({ field: "priority", value: "yes", label: "priority: yes" })
  }
  // Catch "from <name>" patterns
  const fromMatch = q.match(/from\s+(?!internal)(\w+)/)
  if (fromMatch) {
    conditions.push({ field: "from", value: fromMatch[1], label: `from: ${fromMatch[1]}` })
  }

  if (conditions.length === 0 && q.length > 0) {
    conditions.push({ field: "keyword", value: q, label: `keyword: "${q}"` })
  }

  return conditions
}

function deriveFilterName(conditions: FilterCondition[]): string {
  if (conditions.length === 0) return "Untitled Filter"
  return conditions.map(c => c.label).join(" + ")
}

interface FilterModalProps {
  open: boolean
  onClose: () => void
  onSave: (filter: SavedFilter) => void
  onRunOnce: (conditions: FilterCondition[]) => void
  onDelete?: (id: string) => void
  editingFilter?: SavedFilter | null
}

export function FilterModal({
  open,
  onClose,
  onSave,
  onRunOnce,
  onDelete,
  editingFilter,
}: FilterModalProps) {
  const [query, setQuery] = useState("")
  const [conditions, setConditions] = useState<FilterCondition[]>([])

  useEffect(() => {
    if (editingFilter) {
      setQuery(editingFilter.query)
      setConditions(editingFilter.conditions)
    } else {
      setQuery("")
      setConditions([])
    }
  }, [editingFilter, open])

  const handleQueryChange = useCallback((val: string) => {
    setQuery(val)
    setConditions(parseQuery(val))
  }, [])

  const handlePreset = useCallback((presetQuery: string) => {
    const presetConditions = parseQuery(presetQuery)
    setConditions((prev) => {
      // Check if all of this preset's conditions are already active
      const allPresent = presetConditions.every((pc) =>
        prev.some((c) => c.field === pc.field && c.value === pc.value)
      )

      let next: FilterCondition[]
      if (allPresent) {
        // Remove this preset's conditions
        next = prev.filter(
          (c) => !presetConditions.some((pc) => pc.field === c.field && pc.value === c.value)
        )
      } else {
        // Add conditions that aren't already present
        const toAdd = presetConditions.filter(
          (pc) => !prev.some((c) => c.field === pc.field && c.value === pc.value)
        )
        next = [...prev, ...toAdd]
      }

      // Rebuild query text from combined conditions
      setQuery(next.map((c) => c.label).join(", "))
      return next
    })
  }, [])

  const handleSave = useCallback(() => {
    if (conditions.length === 0) return
    const filter: SavedFilter = {
      id: editingFilter?.id ?? `filter-${Date.now()}`,
      name: deriveFilterName(conditions),
      query,
      conditions,
    }
    onSave(filter)
    onClose()
  }, [conditions, query, editingFilter, onSave, onClose])

  const handleRunOnce = useCallback(() => {
    if (conditions.length === 0) return
    onRunOnce(conditions)
    onClose()
  }, [conditions, onRunOnce, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-background/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative z-10 w-full max-w-md rounded-lg border border-border bg-background shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h3 className="text-sm font-medium text-foreground">
            {editingFilter ? "Edit Filter" : "Create Filter"}
          </h3>
          <button
            onClick={onClose}
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4">
          {/* Input */}
          <input
            type="text"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            placeholder="e.g. unread from internal senders"
            className="w-full rounded-md border border-border bg-input px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/50 outline-none transition-colors focus:border-foreground/20 focus:ring-1 focus:ring-ring/20"
            autoFocus
          />

          {/* Parsed conditions preview */}
          <div className="mt-3 min-h-[28px]">
            {conditions.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {conditions.map((c, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
                  >
                    {c.label}
                    {i < conditions.length - 1 && (
                      <span className="ml-1.5 text-muted-foreground/50">+</span>
                    )}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-[10px] text-muted-foreground/40">
                Type a query to see the parsed filter
              </p>
            )}
          </div>

          {/* Divider */}
          <div className="my-4 h-px bg-border" />

          {/* Presets */}
          <div>
            <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Suggestions
            </p>
            <div className="flex flex-wrap gap-1.5">
              {PRESETS.map((preset) => {
                const presetConditions = parseQuery(preset.query)
                const isActive = presetConditions.length > 0 && presetConditions.every((pc) =>
                  conditions.some((c) => c.field === pc.field && c.value === pc.value)
                )
                return (
                  <button
                    key={preset.query}
                    onClick={() => handlePreset(preset.query)}
                    className={cn(
                      "rounded-md border px-2.5 py-1 text-[10px] transition-colors",
                      isActive
                        ? "border-foreground/20 bg-muted text-foreground"
                        : "border-border text-muted-foreground hover:bg-muted hover:text-foreground"
                    )}
                  >
                    {preset.label}
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <div>
            {editingFilter && onDelete && (
              <button
                onClick={() => { onDelete(editingFilter.id); onClose() }}
                className="rounded-md px-3 py-1.5 text-[11px] font-medium text-destructive transition-colors hover:bg-destructive/10"
              >
                Delete
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRunOnce}
              disabled={conditions.length === 0}
              className="rounded-md border border-border px-3 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-40 disabled:pointer-events-none"
            >
              Run Once
            </button>
            <button
              onClick={handleSave}
              disabled={conditions.length === 0}
              className="rounded-md bg-foreground px-3 py-1.5 text-[11px] font-medium text-background transition-colors hover:bg-foreground/90 disabled:opacity-40 disabled:pointer-events-none"
            >
              {editingFilter ? "Update Filter" : "Create Filter"}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

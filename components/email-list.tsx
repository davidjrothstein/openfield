"use client"

import { useState, useMemo, useEffect } from "react"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { Email } from "@/lib/email-data"
import {
  Paperclip,
  Zap,
  ArrowUp,
  ArrowDown,
  Circle,
  CheckCircle2,
  Columns3,
} from "lucide-react"

export type Density = "compact" | "cozy" | "expanded"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

type SortKey = "sender" | "subject" | "date" | "task" | "attachments"
type SortDir = "asc" | "desc"

const allColumns = [
  { key: "task" as const, label: "Task", defaultOn: true },
  { key: "sender" as const, label: "From", defaultOn: true },
  { key: "subject" as const, label: "Subject", defaultOn: true },
  { key: "attachments" as const, label: "Attachments", defaultOn: true },
  { key: "date" as const, label: "Date", defaultOn: true },
]

interface EmailListProps {
  emails: Email[]
  selectedEmailId: string | null
  onSelectEmail: (id: string) => void
  dimmed?: boolean
  activeFolder?: string
  filterLabel?: string | null
  completedTasks?: Set<string>
  dismissedTasks?: Set<string>
  onToggleTask?: (emailId: string) => void
  density?: Density
  onDensityChange?: (d: Density) => void
  layoutMode?: "vertical" | "horizontal" | "cards"
  onLayoutModeChange?: (mode: "vertical" | "horizontal" | "cards") => void
  batchMode?: boolean
  onToggleBatchMode?: () => void
  batchActioned?: boolean
  totalActionEmails?: number
  batchStart?: number
  batchSize?: number
  onNextBatch?: () => void
  hasMoreBatches?: boolean
}

export function EmailList({
  emails,
  selectedEmailId,
  onSelectEmail,
  dimmed = false,
  activeFolder = "inbox",
  filterLabel = null,
  completedTasks = new Set(),
  dismissedTasks = new Set(),
  onToggleTask,
  density = "cozy",
  onDensityChange,
  layoutMode = "vertical",
  onLayoutModeChange,
  batchMode = false,
  onToggleBatchMode,
  batchActioned = false,
  totalActionEmails = 0,
  batchStart = 0,
  batchSize = 0,
  onNextBatch,
  hasMoreBatches = false,
}: EmailListProps) {
  const [sortKey, setSortKey] = useState<SortKey>("date")
  const [sortDir, setSortDir] = useState<SortDir>("desc")
  const [visibleCols, setVisibleCols] = useState<Set<string>>(
    () => new Set(allColumns.filter((c) => c.defaultOn).map((c) => c.key))
  )

  const folderLabels: Record<string, { name: string; context: string }> = {
    inbox: { name: "Inbox", context: "all messages" },
    priority: { name: "Inbox", context: "priority" },
    "action-needed": { name: "Inbox", context: "action needed" },
    informational: { name: "Inbox", context: "informational" },
    newsletters: { name: "Inbox", context: "newsletters" },
    sent: { name: "Sent", context: "all sent" },
    drafts: { name: "Drafts", context: "all drafts" },
  }

  const current = folderLabels[activeFolder] ?? { name: "Inbox", context: "all messages" }
  const contextLabel = filterLabel ? `from ${filterLabel}` : current.context
  const headerLabel = filterLabel
    ? `Filtered Inbox (${contextLabel})`
    : `${current.name} (${contextLabel})`

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(key)
      setSortDir(key === "date" ? "desc" : "asc")
    }
  }

  const toggleCol = (key: string) => {
    setVisibleCols((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        if (next.size > 2) next.delete(key) // keep at least 2 cols
      } else {
        next.add(key)
      }
      return next
    })
  }

  const sorted = useMemo(() => {
    const arr = [...emails]
    const dir = sortDir === "asc" ? 1 : -1
    arr.sort((a, b) => {
      switch (sortKey) {
        case "sender":
          return dir * a.sender.localeCompare(b.sender)
        case "subject":
          return dir * a.subject.localeCompare(b.subject)
        case "task": {
          const aHas = a.actions.length > 0 ? 1 : 0
          const bHas = b.actions.length > 0 ? 1 : 0
          return dir * (aHas - bHas)
        }
        case "attachments": {
          return dir * (a.attachments.length - b.attachments.length)
        }
        case "date":
        default:
          return dir * (emails.indexOf(a) - emails.indexOf(b))
      }
    })
    return arr
  }, [emails, sortKey, sortDir])

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return null
    return sortDir === "asc" ? (
      <ArrowUp className="size-2.5" />
    ) : (
      <ArrowDown className="size-2.5" />
    )
  }

  const show = (key: string) => visibleCols.has(key)

  return (
    <div
      className={cn(
        "flex h-full flex-col overflow-hidden bg-background transition-opacity duration-300",
        dimmed && "opacity-40 pointer-events-none"
      )}
    >
      {/* List Header — hidden in zen card view */}
      <div className={cn("flex items-center justify-between border-b border-border px-4 py-2.5", layoutMode === "cards" && "hidden")}>
        <div className="flex items-center gap-2.5">
          {activeFolder === "priority" && <Zap className="size-3 text-muted-foreground" />}
          <span className="text-xs font-medium text-foreground">
            {headerLabel}
          </span>
          {/* Layout toggle */}
          {onLayoutModeChange && (
            <div className="flex items-center rounded-md border border-border">
              <button
                onClick={() => onLayoutModeChange("vertical")}
                className={cn(
                  "flex items-center justify-center rounded-l-md p-1 transition-colors",
                  layoutMode === "vertical"
                    ? "bg-muted text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
                aria-label="Top-bottom reading pane"
              >
                <svg className="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="8" rx="1" /><rect x="3" y="13" width="18" height="8" rx="1" /></svg>
              </button>
              <button
                onClick={() => onLayoutModeChange("horizontal")}
                className={cn(
                  "flex items-center justify-center p-1 transition-colors",
                  layoutMode === "horizontal"
                    ? "bg-muted text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
                aria-label="Side-by-side reading pane"
              >
                <svg className="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="8" height="18" rx="1" /><rect x="13" y="3" width="8" height="18" rx="1" /></svg>
              </button>
              <button
                onClick={() => onLayoutModeChange("cards")}
                className={cn(
                  "flex items-center justify-center rounded-r-md p-1 transition-colors",
                  layoutMode === "cards"
                    ? "bg-muted text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
                aria-label="Card grid view"
              >
                <svg className="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="8" height="8" rx="1" /><rect x="13" y="3" width="8" height="8" rx="1" /><rect x="3" y="13" width="8" height="8" rx="1" /><rect x="13" y="13" width="8" height="8" rx="1" /></svg>
              </button>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Batch button */}
          {onToggleBatchMode && (
            <button
              onClick={onToggleBatchMode}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-medium transition-colors",
                batchMode
                  ? "bg-foreground text-background"
                  : "border border-border text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
              aria-label={batchMode ? "Exit batch mode" : "Start batch mode"}
            >
              <svg className="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <ellipse cx="12" cy="10" rx="9" ry="6" />
                <path d="M3 10v2c0 3.3 4 6 9 6s9-2.7 9-6v-2" />
                <path d="M7.5 7c1-2 2.5-3 4.5-3s3.5 1 4.5 3" />
                <line x1="7" y1="10" x2="7" y2="16" />
                <line x1="12" y1="10" x2="12" y2="16" />
                <line x1="17" y1="10" x2="17" y2="16" />
              </svg>
              <span>{batchMode ? "Exit Batch" : "Batch"}</span>
            </button>
          )}
          <span className="text-[11px] text-muted-foreground">
            {emails.length} messages
          </span>
          {/* Column visibility toggle */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                aria-label="Toggle columns"
              >
                <Columns3 className="size-3.5" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-36">
              {allColumns.map((col) => (
                <DropdownMenuCheckboxItem
                  key={col.key}
                  checked={visibleCols.has(col.key)}
                  onCheckedChange={() => toggleCol(col.key)}
                  className="text-xs"
                >
                  {col.label}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Column Headers — hidden in card view */}
      <div className={cn("flex items-center gap-3 border-b border-border px-4 py-1.5", layoutMode === "cards" && "hidden")}>
        {/* Unread dot spacer */}
        <span className="w-4 shrink-0" />

        {show("task") && (
          <button
            onClick={() => toggleSort("task")}
            className="flex w-6 shrink-0 items-center justify-center gap-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground"
            aria-label="Sort by task"
          >
            <Circle className="size-2.5" />
            <SortIcon col="task" />
          </button>
        )}

        {show("sender") && (
          <button
            onClick={() => toggleSort("sender")}
            className="flex w-36 shrink-0 items-center gap-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            From
            <SortIcon col="sender" />
          </button>
        )}

        {show("subject") && (
          <button
            onClick={() => toggleSort("subject")}
            className="flex flex-1 items-center gap-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            Subject
            <SortIcon col="subject" />
          </button>
        )}

        {show("attachments") && (
          <button
            onClick={() => toggleSort("attachments")}
            className="flex w-6 shrink-0 items-center justify-center gap-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground"
            aria-label="Sort by attachments"
          >
            <Paperclip className="size-2.5" />
            <SortIcon col="attachments" />
          </button>
        )}

        {show("date") && (
          <button
            onClick={() => toggleSort("date")}
            className="flex w-14 shrink-0 items-center justify-end gap-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            Date
            <SortIcon col="date" />
          </button>
        )}
      </div>

      {/* Card Grid View */}
      {layoutMode === "cards" && (
        <CardGridView
          emails={sorted}
          selectedEmailId={selectedEmailId}
          onSelectEmail={onSelectEmail}
          activeFolder={activeFolder}
          onLayoutModeChange={onLayoutModeChange}
        />
      )}

      {/* Email Rows — hidden in card view */}
      <ScrollArea className={cn("flex-1 overflow-hidden", layoutMode === "cards" && "hidden")}>
        <div>
          {sorted.map((email) => {
  const hasTask = email.actions.length > 0
  const taskDone = completedTasks.has(email.id)
  const taskDismissed = dismissedTasks.has(email.id)
            const isCompact = density === "compact"
            const isExpanded = density === "expanded"
            return (
              <div
                key={email.id}
                role="button"
                tabIndex={0}
                onClick={() => onSelectEmail(email.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    onSelectEmail(email.id)
                  }
                }}
                className={cn(
                  "group flex w-full cursor-pointer gap-3 border-b border-border/40 px-4 text-left transition-colors",
                  isCompact ? "items-center py-1.5" : isExpanded ? "items-start py-3" : "items-start py-2",
                  selectedEmailId === email.id
                    ? "bg-muted"
                    : "hover:bg-muted/50"
                )}
              >
                {/* Unread dot */}
                <div className={cn("flex w-4 shrink-0 items-center justify-center", !isCompact && "pt-1")}>
                  {!email.read && (
                    <div className="size-1.5 rounded-full bg-foreground/60" />
                  )}
                </div>

                {/* Task indicator */}
                {show("task") && (
                  <div className={cn("flex w-6 shrink-0 items-center justify-center", !isCompact && "pt-1")}>
                    {hasTask && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          onToggleTask?.(email.id)
                        }}
                        className={cn(
                          "rounded-full transition-colors",
                          taskDismissed
                            ? "text-muted-foreground/20 hover:text-muted-foreground/40"
                            : taskDone
                              ? "text-foreground/60 hover:text-foreground"
                              : "text-muted-foreground/40 hover:text-foreground/60"
                        )}
                        aria-label={taskDismissed ? "Restore task" : taskDone ? "Dismiss task" : "Mark task complete"}
                      >
                        {taskDismissed ? (
                          <div className="size-3.5 rounded-full border border-current opacity-30" />
                        ) : taskDone ? (
                          <CheckCircle2 className="size-3.5" />
                        ) : (
                          <Circle className="size-3.5" />
                        )}
                      </button>
                    )}
                  </div>
                )}

                {/* Compact: single line with everything inline */}
                {isCompact && (
                  <>
                    {show("sender") && (
                      <span className={cn("w-32 shrink-0 truncate text-[11px]", !email.read ? "font-medium text-foreground" : "text-muted-foreground")}>
                        {email.sender}
                      </span>
                    )}
                    {show("subject") && (
                      <span className={cn("flex-1 truncate text-[11px]", !email.read ? "font-medium text-foreground" : "text-muted-foreground")}>
                        {email.subject}
                      </span>
                    )}
                    {show("attachments") && (
                      <div className="flex w-6 shrink-0 items-center justify-center">
                        {email.attachments.length > 0 && <Paperclip className="size-2.5 text-muted-foreground/40" />}
                      </div>
                    )}
                    {show("date") && (
                      <span className="w-14 shrink-0 text-right text-[10px] text-muted-foreground">{email.timestamp}</span>
                    )}
                  </>
                )}

                {/* Cozy: line 1 = sender - subject, line 2 = preview */}
                {density === "cozy" && (
                  <div className="flex flex-1 gap-3 overflow-hidden">
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
                          {show("sender") && (
                            <span className={cn("shrink-0 text-xs", !email.read ? "font-medium text-foreground" : "text-muted-foreground")}>
                              {email.sender}
                            </span>
                          )}
                          {show("subject") && (
                            <>
                              <span className="shrink-0 text-[11px] text-muted-foreground/40">{"—"}</span>
                              <span className={cn("truncate text-[11px]", !email.read ? "text-foreground/70" : "text-muted-foreground/50")}>
                                {email.subject}
                              </span>
                            </>
                          )}
                        </div>
                        {show("attachments") && email.attachments.length > 0 && (
                          <Paperclip className="size-2.5 shrink-0 text-muted-foreground/40" />
                        )}
                        {show("date") && (
                          <span className="shrink-0 text-[10px] text-muted-foreground">{email.timestamp}</span>
                        )}
                      </div>
                      <span className="truncate text-[11px] leading-relaxed text-muted-foreground/50">
                        {email.preview}
                      </span>
                    </div>
                  </div>
                )}

                {/* Expanded: multi-line with sender, subject, and preview on separate lines */}
                {isExpanded && (
                  <div className="flex flex-1 gap-3 overflow-hidden">
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        {show("sender") && (
                          <span className={cn("shrink-0 text-xs", !email.read ? "font-medium text-foreground" : "text-muted-foreground")}>
                            {email.sender}
                          </span>
                        )}
                        {show("date") && (
                          <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">{email.timestamp}</span>
                        )}
                      </div>
                      {show("subject") && (
                        <span className={cn("truncate text-xs", !email.read ? "font-medium text-foreground" : "text-foreground/70")}>
                          {email.subject}
                        </span>
                      )}
                      <span className="line-clamp-1 text-[11px] leading-relaxed text-muted-foreground/60">
                        {email.preview}
                      </span>
                      {activeFolder === "priority" && email.priorityReason && (
                        <span className="mt-0.5 w-fit truncate rounded bg-muted px-1.5 py-0.5 text-[9px] text-muted-foreground">
                          {email.priorityReason}
                        </span>
                      )}
                    </div>
                    {show("attachments") && email.attachments.length > 0 && (
                      <div className="flex shrink-0 items-start pt-0.5">
                        <Paperclip className="size-3 text-muted-foreground/40" />
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </ScrollArea>

      {/* Batch mode footer */}
      {batchMode && !batchActioned && (
        <div className="flex items-center justify-center border-t border-border px-4 py-2">
          <span className="text-[10px] text-muted-foreground">
            Showing {batchStart + 1}{"–"}{batchStart + batchSize} of{" "}
            <span className="font-medium text-foreground">{totalActionEmails}</span>{" "}
            emails with to-do{"'"}s
          </span>
        </div>
      )}

      {/* Batch complete affirmation */}
      {batchMode && batchActioned && (
        <div className="flex flex-col items-center justify-center gap-3 border-t border-border px-4 py-5">
          <svg className="size-8 text-foreground/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <ellipse cx="12" cy="10" rx="9" ry="6" />
            <path d="M3 10v2c0 3.3 4 6 9 6s9-2.7 9-6v-2" />
            <path d="M7.5 7c1-2 2.5-3 4.5-3s3.5 1 4.5 3" />
            <line x1="7" y1="10" x2="7" y2="16" />
            <line x1="12" y1="10" x2="12" y2="16" />
            <line x1="17" y1="10" x2="17" y2="16" />
          </svg>
          <span className="text-xs font-medium text-foreground">
            Nice work! Batch complete.
          </span>
          {hasMoreBatches ? (
            <button
              onClick={onNextBatch}
              className="rounded-md bg-foreground px-3 py-1.5 text-[11px] font-medium text-background transition-colors hover:bg-foreground/80"
            >
              Load another batch
            </button>
          ) : (
            <span className="text-[10px] text-muted-foreground">
              You{"'"}ve worked through all {totalActionEmails} emails. Take a break!
            </span>
          )}
          <span className="text-[10px] text-muted-foreground">
            {totalActionEmails - batchStart - batchSize > 0
              ? `${totalActionEmails - batchStart - batchSize} more emails with to-do's remaining`
              : "All caught up!"}
          </span>
        </div>
      )}

      {/* Density picker footer — hidden in card view */}
      {onDensityChange && layoutMode !== "cards" && (
        <div className="flex items-center justify-center border-t border-border px-4 py-1.5">
          <div className="flex items-center rounded-md border border-border">
            {(["compact", "cozy", "expanded"] as Density[]).map((d) => (
              <button
                key={d}
                onClick={() => onDensityChange(d)}
                className={cn(
                  "px-2 py-0.5 text-[10px] capitalize transition-colors",
                  d === "compact" && "rounded-l-md",
                  d === "expanded" && "rounded-r-md",
                  density === d
                    ? "bg-muted font-medium text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Zen Focus View ──────────────────────────────────────── */

function priorityScore(e: Email): number {
  let s = 0
  if (!e.read) s += 100
  if (e.priority) s += 50
  if (e.actionRequired) s += 25
  if (e.flagged) s += 10
  return s
}

function importanceTag(e: Email): string | null {
  if (e.actionRequired) return "Action needed"
  if (e.priority && e.priorityReason) return e.priorityReason
  if (e.priority) return "Priority"
  if (e.flagged) return "Flagged"
  if (!e.read) return "Unread"
  return null
}

/* Skeleton for zen loading */
function ZenSkeleton() {
  return (
    <div className="animate-pulse rounded-2xl border border-border bg-card px-8 py-7">
      <div className="flex items-center gap-4">
        <div className="size-11 rounded-full bg-muted" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-36 rounded bg-muted" />
          <div className="h-3 w-20 rounded bg-muted" />
        </div>
        <div className="h-3 w-14 rounded bg-muted" />
      </div>
      <div className="mt-5 h-5 w-3/4 rounded bg-muted" />
      <div className="mt-3 space-y-2">
        <div className="h-3.5 w-full rounded bg-muted" />
        <div className="h-3.5 w-5/6 rounded bg-muted" />
      </div>
    </div>
  )
}

interface CardGridViewProps {
  emails: Email[]
  selectedEmailId: string | null
  onSelectEmail: (id: string) => void
  activeFolder?: string
  onLayoutModeChange?: (mode: "vertical" | "horizontal" | "cards") => void
}

function CardGridView({ emails, selectedEmailId, onSelectEmail, activeFolder, onLayoutModeChange }: CardGridViewProps) {
  const [loading, setLoading] = useState(true)
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [doneForNow, setDoneForNow] = useState(false)

  useEffect(() => {
    setLoading(true)
    setDismissed(new Set())
    setDoneForNow(false)
    const t = setTimeout(() => setLoading(false), 500)
    return () => clearTimeout(t)
  }, [activeFolder])

  // Top 5 priority emails, excluding dismissed
  const ranked = useMemo(() =>
    [...emails]
      .filter((e) => !dismissed.has(e.id))
      .sort((a, b) => priorityScore(b) - priorityScore(a))
      .slice(0, 5),
  [emails, dismissed])

  const handleArchive = (id: string) => {
    setDismissed((prev) => new Set(prev).add(id))
  }

  if (loading) {
    return (
      <div className="flex flex-1 flex-col items-center justify-start overflow-auto bg-background px-6 py-16">
        <div className="w-full max-w-xl space-y-5">
          <div className="mb-8 space-y-1">
            <div className="h-6 w-48 animate-pulse rounded bg-muted" />
            <div className="h-3.5 w-64 animate-pulse rounded bg-muted" />
          </div>
          <ZenSkeleton />
          <ZenSkeleton />
          <ZenSkeleton />
        </div>
      </div>
    )
  }

  if (doneForNow || ranked.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center bg-background px-6">
        <div className="flex flex-col items-center gap-5 text-center">
          <div className="flex size-14 items-center justify-center rounded-full bg-muted/50">
            <svg className="size-6 text-muted-foreground/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z" />
              <path d="M8 14s1.5 2 4 2 4-2 4-2" />
              <line x1="9" y1="9" x2="9.01" y2="9" />
              <line x1="15" y1="9" x2="15.01" y2="9" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium text-foreground/80">{"You're all caught up"}</p>
            <p className="mt-1 text-xs text-muted-foreground/50">Nothing urgent right now. Enjoy the quiet.</p>
          </div>
          <button
            onClick={() => onLayoutModeChange?.("vertical")}
            className="mt-2 rounded-lg px-4 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            Back to inbox
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-auto bg-background">
      <div className="mx-auto w-full max-w-xl px-6 py-12">
        {/* Quiet header */}
        <div className="mb-10 flex items-end justify-between">
          <div>
            <h2 className="text-balance text-lg font-semibold tracking-tight text-foreground">
              Today's focus
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground/50">
              {ranked.length} {ranked.length === 1 ? "thing" : "things"} that need your attention
            </p>
          </div>
          <button
            onClick={() => onLayoutModeChange?.("vertical")}
            className="rounded-md px-2.5 py-1 text-[11px] text-muted-foreground/40 transition-colors hover:text-muted-foreground"
          >
            Exit
          </button>
        </div>

        {/* Card stack */}
        <div className="flex flex-col gap-5">
          {ranked.map((email, i) => {
            const tag = importanceTag(email)
            return (
              <div
                key={email.id}
                className={cn(
                  "zen-card group relative rounded-2xl border bg-card transition-all duration-300",
                  !email.read
                    ? "border-l-[3px] border-l-primary border-b-[2px] border-b-primary border-r-border border-t-border"
                    : "border-border",
                  selectedEmailId === email.id && "ring-1 ring-primary/30"
                )}
              >
                <div className="px-7 py-6">
                  {/* Sender row */}
                  <div className="flex items-center gap-4">
                    <div className={cn(
                      "flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-bold",
                      !email.read ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
                    )}>
                      {email.sender.charAt(0)}
                    </div>
                    <div className="flex-1">
                      <p className={cn(
                        "text-sm",
                        !email.read ? "font-semibold text-foreground" : "text-foreground/70"
                      )}>
                        {email.sender}
                      </p>
                      {email.senderTitle && (
                        <p className="text-[11px] text-muted-foreground/40">{email.senderTitle}</p>
                      )}
                    </div>
                    <span className="text-[11px] text-muted-foreground/40">{email.timestamp}</span>
                  </div>

                  {/* Subject */}
                  <p className={cn(
                    "mt-4 text-pretty text-[15px] leading-snug",
                    !email.read ? "font-semibold text-foreground" : "text-foreground/80"
                  )}>
                    {email.subject}
                  </p>

                  {/* AI summary */}
                  {email.threadSummary?.[0] && (
                    <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground/60">
                      {email.threadSummary[0]}
                    </p>
                  )}

                  {/* Tag */}
                  {tag && (
                    <div className="mt-4">
                      <span className="rounded-md bg-primary/8 px-2 py-0.5 text-[10px] font-medium text-primary/70">
                        {tag}
                      </span>
                    </div>
                  )}
                </div>

                {/* Action bar — appears on hover */}
                <div className="flex items-center gap-2 border-t border-border/50 px-7 py-3 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                  <button
                    onClick={() => onSelectEmail(email.id)}
                    className="rounded-md px-3 py-1.5 text-[11px] font-medium text-foreground/70 transition-colors hover:bg-muted hover:text-foreground"
                  >
                    Open
                  </button>
                  <button
                    onClick={() => handleArchive(email.id)}
                    className="rounded-md px-3 py-1.5 text-[11px] font-medium text-muted-foreground/50 transition-colors hover:bg-muted hover:text-foreground"
                  >
                    Done
                  </button>
                </div>
              </div>
            )
          })}
        </div>

        {/* Off-ramp */}
        <div className="mt-12 flex justify-center pb-12">
          <button
            onClick={() => setDoneForNow(true)}
            className="rounded-lg px-5 py-2.5 text-xs font-medium text-muted-foreground/40 transition-colors hover:bg-muted/50 hover:text-muted-foreground"
          >
            {"That's enough for now"}
          </button>
        </div>
      </div>
    </div>
  )
}

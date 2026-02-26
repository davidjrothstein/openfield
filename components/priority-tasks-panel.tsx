"use client"

import { useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ListTodo, Clock, ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

interface Email {
  id: string
  sender: string
  subject: string
  preview: string
}

interface PriorityTasksPanelProps {
  manualTodos?: Array<{ id: string; text: string }>
  smartTodos?: Array<{ id: string; text: string }>
  onToggle?: (id: string) => void
  emails?: Email[]
  onSelectEmail?: (id: string) => void
  onShowDashboard?: () => void
}

type SortType = "urgency" | "deadline"

export function PriorityTasksPanel({
  emails = [],
  onSelectEmail,
  onShowDashboard,
}: PriorityTasksPanelProps) {
  const [sortBy, setSortBy] = useState<SortType>("urgency")
  const [snoozed, setSnoozed] = useState<Set<string>>(new Set())
  const [deprioritized, setDeprioritized] = useState<Set<string>>(new Set())

  const taskEmails = emails
    .filter((e) => e.preview.length > 0 && !snoozed.has(e.id) && !deprioritized.has(e.id))
    .slice(0, 15)

  return (
    <div className="flex h-full flex-col overflow-hidden bg-secondary">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
        <ListTodo className="size-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-foreground">Triage</span>
        <span className="ml-auto text-[10px] text-muted-foreground">
          {taskEmails.length}
        </span>
        {onShowDashboard && (
          <button
            onClick={onShowDashboard}
            className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
          >
            Dashboard
          </button>
        )}
      </div>

      {/* Sort Controls */}
      <div className="flex items-center gap-1.5 border-b border-border/50 px-4 py-2 bg-muted/20">
        <span className="text-[10px] text-muted-foreground">Sort by</span>
        <div className="flex gap-1">
          {(["urgency", "deadline"] as const).map((sort) => (
            <button
              key={sort}
              onClick={() => setSortBy(sort)}
              className={cn(
                "rounded-md px-2 py-1 text-[10px] font-medium transition-colors",
                sortBy === sort
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              {sort === "urgency" ? "Urgency" : "Deadline"}
            </button>
          ))}
        </div>
      </div>

      <ScrollArea className="flex-1 overflow-hidden">
        <div className="divide-y divide-border/50">
          {taskEmails.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center px-4">
              <ListTodo className="mb-2 size-5 text-muted-foreground/30" />
              <p className="text-xs text-muted-foreground">No items to triage</p>
            </div>
          ) : (
            taskEmails.map((email) => (
              <div
                key={email.id}
                className="group flex items-stretch border-b border-border/50 transition-colors hover:bg-muted/30"
              >
                {/* Left action buttons */}
                <div className="flex items-center gap-0.5 px-2 py-3 opacity-0 group-hover:opacity-100 transition-opacity">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setSnoozed((prev) => new Set(prev).add(email.id))
                        }}
                        className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                        aria-label="Snooze"
                      >
                        <Clock className="size-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="right" className="text-xs">Snooze</TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeprioritized((prev) => new Set(prev).add(email.id))
                        }}
                        className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                        aria-label="Deprioritize"
                      >
                        <ChevronDown className="size-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="right" className="text-xs">Deprioritize</TooltipContent>
                  </Tooltip>
                </div>

                {/* Content */}
                <button
                  onClick={() => onSelectEmail?.(email.id)}
                  className="flex-1 text-left px-4 py-3 transition-colors focus:outline-none"
                >
                  {/* Line 1: Sender / Subject */}
                  <div className="flex items-baseline gap-2 mb-1 min-w-0">
                    <span className="text-[11px] font-medium text-foreground shrink-0">
                      {email.sender.split(" ")[0]}
                    </span>
                    <span className="text-[10px] text-muted-foreground truncate">
                      {email.subject.length > 35
                        ? email.subject.substring(0, 35) + "…"
                        : email.subject}
                    </span>
                  </div>
                  {/* Line 2: Preview */}
                  <p className="text-[10px] text-muted-foreground leading-tight line-clamp-2">
                    {email.preview}
                  </p>
                </button>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

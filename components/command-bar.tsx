"use client"

import { useEffect, useRef } from "react"
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog"
import { Search, ArrowRight, Clock } from "lucide-react"

const recentCommands = [
  "Summarize last week's emails from Marcus Chen",
  "Find emails about the Henderson contract",
  "Draft a follow-up to the Series B thread",
  "Show all flagged emails with pending actions",
  "List all invoices due this month",
]

interface CommandBarProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CommandBar({ open, onOpenChange }: CommandBarProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="top-[30%] max-w-xl translate-y-0 gap-0 overflow-hidden rounded-xl border-border bg-background p-0 shadow-lg sm:max-w-xl"
      >
        <DialogTitle className="sr-only">Command Palette</DialogTitle>
        {/* Input */}
        <div className="flex items-center gap-3 border-b border-border px-4 py-3">
          <Search className="size-4 shrink-0 text-muted-foreground" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search or type a command..."
            className="w-full bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none"
          />
        </div>

        {/* Quick Actions */}
        <div className="border-b border-border px-4 py-3">
          <span className="text-[10px] font-medium text-muted-foreground">
            Quick actions
          </span>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {[
              "Compose new email",
              "Search all threads",
              "Show unread",
              "Go to drafts",
            ].map((action) => (
              <button
                key={action}
                className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <ArrowRight className="size-2.5" />
                {action}
              </button>
            ))}
          </div>
        </div>

        {/* Recent Commands */}
        <div className="max-h-56 overflow-auto px-2 py-2">
          <div className="px-2 pb-1.5">
            <span className="text-[10px] font-medium text-muted-foreground">
              Recent
            </span>
          </div>
          {recentCommands.map((cmd, i) => (
            <button
              key={i}
              className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors hover:bg-muted"
            >
              <Clock className="size-3 shrink-0 text-muted-foreground/40" />
              <span className="flex-1 text-xs text-foreground/70">
                {cmd}
              </span>
              <ArrowRight className="size-3 shrink-0 text-muted-foreground/20" />
            </button>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border px-4 py-2">
          <div className="flex items-center gap-3">
            <span className="text-[10px] text-muted-foreground">
              Esc to close
            </span>
            <span className="text-[10px] text-muted-foreground">
              Enter to run
            </span>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

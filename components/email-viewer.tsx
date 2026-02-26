"use client"

import { useState, useEffect, useRef } from "react"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { Email } from "@/lib/email-data"
import {
  Reply,
  Forward,
  Archive,
  Flag,
  MoreHorizontal,
  Sparkles,
  Send,
  Paperclip,
  X,
} from "lucide-react"

interface EmailViewerProps {
  email: Email | null
  pendingDraft?: string | null
  onDraftConsumed?: () => void
  onReplyOpenChange?: (open: boolean) => void
  showCloseButton?: boolean
  onClose?: () => void
  focusMode?: boolean
}

export function EmailViewer({ email, pendingDraft, onDraftConsumed, onReplyOpenChange, showCloseButton, onClose, focusMode }: EmailViewerProps) {
  const [showAiDraft, setShowAiDraft] = useState(false)
  const [replyText, setReplyText] = useState("")
  const [replyOpen, setReplyOpen] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // When a draft arrives from the context panel, open the reply and fill it in
  useEffect(() => {
    if (pendingDraft) {
      setReplyText(pendingDraft)
      setReplyOpen(true)
      onDraftConsumed?.()
      // Focus the textarea after a tick
      setTimeout(() => {
        textareaRef.current?.focus()
      }, 100)
    }
  }, [pendingDraft, onDraftConsumed])

  // Notify parent when reply opens/closes
  useEffect(() => {
    onReplyOpenChange?.(replyOpen)
  }, [replyOpen, onReplyOpenChange])

  // Reset reply when email changes
  useEffect(() => {
    setReplyText("")
    setReplyOpen(false)
    setShowAiDraft(false)
  }, [email?.id])

  if (!email) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-1.5 text-muted-foreground">
          <p className="text-sm">No message selected</p>
          <p className="text-xs text-muted-foreground/60">
            Choose an email from the list above
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background">
      {/* Toolbar */}
      <div className={cn("flex items-center gap-1 border-b border-border py-2", focusMode ? "px-4" : "px-4")}>
        {showCloseButton && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={onClose}
                className="mr-1 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                aria-label="Close"
              >
                <X className="size-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent>Close</TooltipContent>
          </Tooltip>
        )}
        {[
          { icon: Reply, label: "Reply", onClick: () => setReplyOpen(true) },
          { icon: Forward, label: "Forward" },
          { icon: Archive, label: "Archive" },
          { icon: Flag, label: "Flag" },
        ].map(({ icon: Icon, label, onClick }) => (
          <Tooltip key={label}>
            <TooltipTrigger asChild>
              <button
                onClick={onClick}
                className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                aria-label={label}
              >
                <Icon className="size-3.5" />
                <span className="hidden text-xs sm:inline">{label}</span>
              </button>
            </TooltipTrigger>
            <TooltipContent>{label}</TooltipContent>
          </Tooltip>
        ))}
        <div className="ml-auto">
          <button
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="More options"
          >
            <MoreHorizontal className="size-3.5" />
          </button>
        </div>
      </div>

      {/* Scrollable content area — centered in focus mode */}
      <ScrollArea className="flex-1 overflow-hidden">
        <div className={cn(focusMode && "flex justify-center")}>
          <div className={cn(focusMode ? "w-full max-w-2xl px-12 py-0" : "w-full")}>

            {/* Email Header */}
            <div className="border-b border-border px-5 py-4">
              <h2 className="text-sm font-medium text-foreground leading-snug text-balance">
                {email.subject}
              </h2>
              <div className="mt-3 flex items-center gap-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium text-foreground">
                  {email.sender.charAt(0)}
                </div>
                <div className="flex flex-col">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button className="text-sm font-medium text-foreground hover:underline text-left">
                        {email.sender}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="max-w-xs">
                      <div className="flex flex-col gap-0.5 p-0.5">
                        <span className="text-xs font-medium">{email.sender}</span>
                        <span className="text-[11px] text-muted-foreground">
                          {email.senderTitle}, {email.senderCompany}
                        </span>
                        <span className="text-[11px] text-muted-foreground">
                          {email.senderEmail}
                        </span>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                  <span className="text-[11px] text-muted-foreground">
                    to me &middot; {email.timestamp}
                  </span>
                </div>
              </div>
            </div>

            {/* Email Body */}
            <div className="select-text px-5 py-5">
              {email.body.map((paragraph, i) => (
                <p
                  key={i}
                  className={cn(
                    "text-[13px] leading-relaxed text-foreground/80 whitespace-pre-line",
                    i > 0 && "mt-3"
                  )}
                >
                  {paragraph}
                </p>
              ))}
            </div>

          </div>
        </div>
      </ScrollArea>

      {/* Compose / Reply Bar */}
      <div className="border-t border-border">
        <div className={cn(focusMode && "flex justify-center")}>
        <div className={cn(focusMode ? "w-full max-w-2xl px-12" : "w-full")}>
        {/* AI Draft Bar */}
        {showAiDraft && (
          <div className="border-b border-border bg-muted/50 px-4 py-3">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="size-3 text-muted-foreground" />
              <span className="text-[11px] font-medium text-muted-foreground">
                Suggested reply
              </span>
              <button
                onClick={() => setShowAiDraft(false)}
                className="ml-auto text-[11px] text-muted-foreground hover:text-foreground"
              >
                Dismiss
              </button>
            </div>
            <p className="text-xs text-foreground/70 leading-relaxed">
              {"Hi " + email.sender.split(" ")[0] + ", thanks for the email. I've reviewed the details and will follow up shortly."}
            </p>
            <div className="mt-2 flex gap-2">
              <button
                onClick={() => {
                  setReplyText(
                    "Hi " + email.sender.split(" ")[0] + ", thanks for the email. I've reviewed the details and will follow up shortly."
                  )
                  setShowAiDraft(false)
                  setReplyOpen(true)
                }}
                className="rounded-md bg-foreground px-2.5 py-1 text-[11px] font-medium text-background transition-colors hover:bg-foreground/80"
              >
                Use draft
              </button>
              <button
                onClick={() => setShowAiDraft(false)}
                className="rounded-md border border-border px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-muted"
              >
                Regenerate
              </button>
            </div>
          </div>
        )}

        {replyOpen ? (
          <div className="flex min-h-0 flex-1 flex-col gap-2 px-4 py-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium text-muted-foreground">
                Reply to {email.sender}
              </span>
              <button
                onClick={() => {
                  setReplyOpen(false)
                  setReplyText("")
                }}
                className="text-[11px] text-muted-foreground hover:text-foreground transition-colors"
              >
                Cancel
              </button>
            </div>
            <textarea
              ref={textareaRef}
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              placeholder="Write a reply..."
              className="select-text min-h-[160px] w-full flex-1 resize-none rounded-md border border-border bg-muted/50 px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground/50 focus:border-foreground/20 focus:outline-none transition-colors leading-relaxed"
            />
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <button
                  className="shrink-0 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  aria-label="Attach file"
                >
                  <Paperclip className="size-3.5" />
                </button>
                <button
                  onClick={() => setShowAiDraft(!showAiDraft)}
                  className={cn(
                    "shrink-0 flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] transition-colors",
                    showAiDraft
                      ? "border-foreground/20 bg-muted text-foreground"
                      : "border-border text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  <Sparkles className="size-3" />
                  <span className="hidden sm:inline">AI</span>
                </button>
              </div>
              <button
                className="flex items-center gap-1.5 rounded-md bg-foreground px-3 py-1.5 text-[11px] font-medium text-background transition-colors hover:bg-foreground/80"
                aria-label="Send reply"
              >
                <Send className="size-3" />
                <span>Send</span>
              </button>
            </div>
          </div>
        ) : (
          <div className="px-4 py-3">
            <button
              onClick={() => setReplyOpen(true)}
              className="w-full rounded-md border border-border bg-muted/50 px-3 py-2 text-left text-xs text-muted-foreground/50 transition-colors hover:border-foreground/10 hover:text-muted-foreground"
            >
              Write a reply...
            </button>
          </div>
        )}
        </div>
        </div>
      </div>
    </div>
  )
}

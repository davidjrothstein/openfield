"use client"

import { useState, useEffect } from "react"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { Email } from "@/lib/email-data"
import {
  Sparkles,
  X,
  Plus,
  ChevronDown,
  ChevronUp,
  Send,
  Paperclip,
  FileText,
  FileSpreadsheet,
  File,
  Download,
  Pen,
  Circle,
  CheckCircle2,
  Reply,
  ListTodo,
  PanelRightClose,
} from "lucide-react"

interface AiContextPanelProps {
  email: Email | null
  onDraftReply: (draft: string) => void
  onShowDashboard?: () => void
  onGenerateDraft?: (draft: string) => void
  focusMode?: boolean
  onCollapseContext?: () => void
  theme?: string
}

export function AiContextPanel({ email, onDraftReply, onShowDashboard, onGenerateDraft, focusMode, onCollapseContext, theme }: AiContextPanelProps) {
  const [expandedSummary, setExpandedSummary] = useState(true)
  const [aiQuery, setAiQuery] = useState("")
  const [isGeneratingDraft, setIsGeneratingDraft] = useState(false)
  // Actions that user wants included in the reply
  const [replyActions, setReplyActions] = useState<Set<string>>(new Set())
  // Actions converted to to-do items
  const [todoActions, setTodoActions] = useState<Set<string>>(new Set())
  // Actions the user has explicitly ignored
  const [ignoredActions, setIgnoredActions] = useState<Set<string>>(new Set())

  // Reset action states when email changes
  useEffect(() => {
    setReplyActions(new Set())
    setTodoActions(new Set())
    setIgnoredActions(new Set())
    setExpandedSummary(true)
  }, [email?.id])

  if (!email) {
    return (
      <div className={cn("flex h-full flex-col items-center justify-center overflow-hidden bg-secondary", theme === "superblue" && "superblue-context")}>
        <div className="flex flex-col items-center gap-2 px-6 text-center">
          <Sparkles className="size-5 text-muted-foreground/30" />
          <p className="text-xs text-muted-foreground">
            Select an email to see details and suggested actions
          </p>
        </div>
      </div>
    )
  }

  const addToReply = (id: string) => {
    setReplyActions((prev) => new Set(prev).add(id))
    setTodoActions((prev) => { const n = new Set(prev); n.delete(id); return n })
    setIgnoredActions((prev) => { const n = new Set(prev); n.delete(id); return n })
  }

  const removeFromReply = (id: string) => {
    setReplyActions((prev) => { const n = new Set(prev); n.delete(id); return n })
  }

  const addToTodo = (id: string) => {
    setTodoActions((prev) => new Set(prev).add(id))
    setReplyActions((prev) => { const n = new Set(prev); n.delete(id); return n })
    setIgnoredActions((prev) => { const n = new Set(prev); n.delete(id); return n })
  }

  const removeFromTodo = (id: string) => {
    setTodoActions((prev) => { const n = new Set(prev); n.delete(id); return n })
  }

  const ignoreAction = (id: string) => {
    setIgnoredActions((prev) => new Set(prev).add(id))
    setReplyActions((prev) => { const n = new Set(prev); n.delete(id); return n })
    setTodoActions((prev) => { const n = new Set(prev); n.delete(id); return n })
  }

  const unignoreAction = (id: string) => {
    setIgnoredActions((prev) => { const n = new Set(prev); n.delete(id); return n })
  }

  const handleDraftReply = () => {
    // Build draft text from the selected action items
    const selectedItems = email.actions.filter((a) => replyActions.has(a.id))
    const greeting = `Hi ${email.sender.split(" ")[0]},`
    const lines = selectedItems.map((item) => {
      // Generate a simple response line for each action
      return `- Re: ${item.text}`
    })
    const draft = [
      greeting,
      "",
      "Following up on the items below:",
      "",
      ...lines,
      "",
      "Please let me know if you need anything else.",
      "",
      "Best regards",
    ].join("\n")

    onDraftReply(draft)
  }

  const hasReplyItems = replyActions.size > 0

  const fileIcon = (type: string) => {
    switch (type) {
      case "pdf":
        return <FileText className="size-3.5 text-muted-foreground" />
      case "spreadsheet":
        return <FileSpreadsheet className="size-3.5 text-muted-foreground" />
      default:
        return <File className="size-3.5 text-muted-foreground" />
    }
  }

  return (
    <div className={cn("flex h-full flex-col overflow-hidden bg-secondary", theme === "superblue" && "superblue-context")}>
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
        <Sparkles className="size-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-foreground">Context</span>
        {onShowDashboard && (
          <button
            onClick={onShowDashboard}
            className="ml-auto text-[10px] text-muted-foreground hover:text-foreground transition-colors"
          >
            Dashboard
          </button>
        )}
        {focusMode && onCollapseContext && (
          <button
            onClick={onCollapseContext}
            className={cn(
              "rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
              !onShowDashboard && "ml-auto"
            )}
            aria-label="Collapse context panel"
          >
            <PanelRightClose className="size-3.5" />
          </button>
        )}
      </div>

      <ScrollArea className="flex-1 overflow-hidden">
        <div className="select-text space-y-5 p-4">
          {/* 1. Attachments (always shown) */}
          <section>
            <div className="mb-2 flex items-center gap-2">
              <Paperclip className="size-3 text-muted-foreground" />
              <SectionLabel as="span">Attachments</SectionLabel>
              {email.attachments.length > 0 && (
                <span className="ml-auto text-[10px] text-muted-foreground">
                  {email.attachments.length}
                </span>
              )}
            </div>
            {email.attachments.length > 0 ? (
              <div className="space-y-1">
                {email.attachments.map((attachment) => (
                  <div
                    key={attachment.name}
                    className="group flex items-center gap-2.5 rounded-md bg-muted px-2.5 py-2 transition-colors hover:bg-muted/80"
                  >
                    {fileIcon(attachment.type)}
                    <div className="flex flex-1 flex-col overflow-hidden">
                      <span className="truncate text-[11px] font-medium text-foreground">
                        {attachment.name}
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        {attachment.size}
                      </span>
                    </div>
                    <button
                      className="shrink-0 rounded p-0.5 text-muted-foreground/40 opacity-0 transition-all hover:text-foreground group-hover:opacity-100"
                      aria-label={`Download ${attachment.name}`}
                    >
                      <Download className="size-3" />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center justify-center rounded-md bg-muted px-3 py-3">
                <span className="text-[11px] text-muted-foreground/50">
                  No attachments
                </span>
              </div>
            )}
          </section>

          {/* 2. Summary */}
          <section>
            <button
              onClick={() => setExpandedSummary(!expandedSummary)}
              className="mb-2 flex w-full items-center justify-between"
            >
              <SectionLabel as="span">Summary</SectionLabel>
              {expandedSummary ? (
                <ChevronUp className="size-3 text-muted-foreground" />
              ) : (
                <ChevronDown className="size-3 text-muted-foreground" />
              )}
            </button>
            {expandedSummary && (
              <div className="rounded-md bg-muted p-3">
                <ul className="space-y-1.5">
                  {email.threadSummary.map((point, i) => (
                    <li key={i} className="flex gap-2 text-[11px] leading-relaxed text-foreground/70">
                      <span className="mt-1.5 block size-1 shrink-0 rounded-full bg-muted-foreground/30" />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {/* 3. To Do */}
          {email.actions.filter((a) => a.type === "todo").length > 0 && (
            <section>
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <ListTodo className="size-3 text-muted-foreground" />
                  <SectionLabel as="span">To Do</SectionLabel>
                </div>
                {todoActions.size > 0 && (
                  <span className="text-[10px] text-foreground/50">
                    {todoActions.size} added
                  </span>
                )}
              </div>
              <div className="space-y-1.5">
                {email.actions
                  .filter((a) => a.type === "todo")
                  .map((action) => {
                    const isInTodo = todoActions.has(action.id)
                    const isIgnored = ignoredActions.has(action.id)
                    return (
                      <div
                        key={action.id}
                        className={cn(
                          "rounded-md border p-2.5 transition-colors",
                          isIgnored
                            ? "border-border/50 bg-muted/30"
                            : isInTodo
                              ? "border-foreground/15 bg-muted"
                              : "border-border bg-muted"
                        )}
                      >
                        <div className="flex items-start gap-2">
                          <button
                            onClick={() =>
                              isInTodo
                                ? removeFromTodo(action.id)
                                : isIgnored
                                  ? unignoreAction(action.id)
                                  : addToTodo(action.id)
                            }
                            className="mt-0.5 shrink-0"
                            aria-label={isInTodo ? "Remove from to do" : "Add to do"}
                          >
                            {isInTodo ? (
                              <CheckCircle2 className="size-3.5 text-foreground/60" />
                            ) : (
                              <Circle className="size-3.5 text-muted-foreground/40" />
                            )}
                          </button>
                          <p
                            className={cn(
                              "flex-1 text-[11px] leading-relaxed",
                              isIgnored
                                ? "text-muted-foreground/50 line-through"
                                : isInTodo
                                  ? "text-foreground/60"
                                  : "text-foreground/80"
                            )}
                          >
                            {action.text}
                          </p>
                        </div>
                        {!isInTodo && !isIgnored && (
                          <div className="mt-1.5 flex gap-1.5 pl-5">
                            <button
                              onClick={() => ignoreAction(action.id)}
                              className="flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                            >
                              <X className="size-2.5" />
                              Ignore
                            </button>
                            <button
                              onClick={() => addToTodo(action.id)}
                              className="flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                            >
                              <Plus className="size-2.5" />
                              Add
                            </button>
                          </div>
                        )}
                        {isIgnored && (
                          <div className="mt-1.5 pl-5">
                            <button
                              onClick={() => unignoreAction(action.id)}
                              className="text-[10px] text-muted-foreground/50 transition-colors hover:text-muted-foreground"
                            >
                              Undo
                            </button>
                          </div>
                        )}
                      </div>
                    )
                  })}
              </div>
            </section>
          )}

          {/* 4. Reply Suggestions */}
          {email.actions.filter((a) => a.type === "reply").length > 0 && (
            <section>
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Reply className="size-3 text-muted-foreground" />
                  <SectionLabel as="span">Reply Suggestions</SectionLabel>
                </div>
                {replyActions.size > 0 && (
                  <span className="text-[10px] text-foreground/50">
                    {replyActions.size} selected
                  </span>
                )}
              </div>
              <div className="space-y-1.5">
                {email.actions
                  .filter((a) => a.type === "reply")
                  .map((action) => {
                    const isInReply = replyActions.has(action.id)
                    const isIgnored = ignoredActions.has(action.id)
                    return (
                      <div
                        key={action.id}
                        className={cn(
                          "rounded-md border p-2.5 transition-colors",
                          isIgnored
                            ? "border-border/50 bg-muted/30"
                            : isInReply
                              ? "border-foreground/15 bg-muted"
                              : "border-border bg-muted"
                        )}
                      >
                        <div className="flex items-start gap-2">
                          <Reply
                            className={cn(
                              "mt-0.5 size-3 shrink-0",
                              isInReply ? "text-foreground/60" : "text-muted-foreground/40"
                            )}
                          />
                          <p
                            className={cn(
                              "flex-1 text-[11px] leading-relaxed",
                              isIgnored
                                ? "text-muted-foreground/50 line-through"
                                : "text-foreground/80"
                            )}
                          >
                            {action.text}
                          </p>
                        </div>
                        <div className="mt-1.5 flex gap-1.5 pl-5">
                          {isIgnored ? (
                            <button
                              onClick={() => unignoreAction(action.id)}
                              className="text-[10px] text-muted-foreground/50 transition-colors hover:text-muted-foreground"
                            >
                              Undo
                            </button>
                          ) : isInReply ? (
                            <button
                              onClick={() => removeFromReply(action.id)}
                              className="flex items-center gap-1 rounded-md border border-foreground/20 bg-foreground px-2 py-0.5 text-[10px] font-medium text-background transition-colors hover:bg-foreground/80"
                            >
                              <Plus className="size-2.5 rotate-45" />
                              In reply
                            </button>
                          ) : (
                            <>
                              <button
                                onClick={() => ignoreAction(action.id)}
                                className="flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                              >
                                <X className="size-2.5" />
                                Ignore
                              </button>
                              <button
                                onClick={() => {
                                  addToReply(action.id)
                                  onDraftReply(action.text + " ")
                                }}
                                className="flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                              >
                                <Plus className="size-2.5" />
                                Add
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    )
                  })}

              {/* Draft Reply button */}
              {hasReplyItems && (
                <button
                  onClick={handleDraftReply}
                  className="mt-2 flex w-full items-center justify-center gap-2 rounded-md bg-foreground px-3 py-2 text-xs font-medium text-background transition-colors hover:bg-foreground/80"
                >
                  <Pen className="size-3" />
                  Draft Reply
                </button>
              )}
              </div>
            </section>
          )}


        </div>
      </ScrollArea>

      {/* AI Chat Input */}
      <div className="border-t border-border p-3">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={aiQuery}
              onChange={(e) => setAiQuery(e.target.value)}
              placeholder="Ask about this email..."
              className="w-full rounded-md border border-border bg-muted/50 py-2 pl-3 pr-8 text-[11px] text-foreground placeholder:text-muted-foreground/40 focus:border-foreground/20 focus:outline-none transition-colors"
            />
            <button
              className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-muted-foreground/40 transition-colors hover:text-foreground"
              aria-label="Send"
            >
              <Send className="size-3" />
            </button>
          </div>
        </div>
        <div className="mt-3 space-y-2">
          {/* Reply actions */}
          <div className="flex gap-2">
            <button
              onClick={() => onDraftReply("")}
              className="flex-1 flex items-center justify-center gap-1 rounded-md border border-border px-2 py-1.5 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <Reply className="size-3" />
              Reply
            </button>
            <button
              onClick={() => onDraftReply("")}
              className="flex-1 flex items-center justify-center gap-1 rounded-md border border-border px-2 py-1.5 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <Reply className="size-3" />
              Reply All
            </button>
          </div>

          {/* Draft reply primary button */}
          <button
            onClick={async () => {
              setIsGeneratingDraft(true)
              try {
                const response = await fetch('/api/draft-reply', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    emailSubject: email?.subject,
                    emailSender: email?.sender,
                    emailBody: email?.body?.join('\n'),
                    emailPreview: email?.preview,
                  }),
                })

                if (!response.ok) throw new Error('Failed to generate draft')

                let draftText = ''
                const reader = response.body?.getReader()
                const decoder = new TextDecoder()

                if (reader) {
                  while (true) {
                    const { done, value } = await reader.read()
                    if (done) break
                    draftText += decoder.decode(value, { stream: true })
                    onGenerateDraft?.(draftText)
                  }
                }
              } catch (error) {
                console.error('[v0] Draft generation error:', error)
              } finally {
                setIsGeneratingDraft(false)
              }
            }}
            disabled={isGeneratingDraft}
            className="w-full flex items-center justify-center gap-2 rounded-md bg-foreground px-3 py-2 text-[11px] font-semibold text-background transition-colors hover:bg-foreground/90 disabled:opacity-50"
          >
            <Sparkles className="size-3.5" />
            {isGeneratingDraft ? 'Generating...' : 'Draft Reply'}
          </button>

          {/* Secondary AI actions */}
          <div className="flex gap-1.5">
            {["Summarize", "Extract dates"].map((cmd) => (
              <button
                key={cmd}
                onClick={() => setAiQuery(cmd)}
                className="flex-1 rounded-md border border-border/50 px-2 py-1 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                {cmd}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function SectionLabel({
  children,
  as: Component = "h3",
}: {
  children: React.ReactNode
  as?: "h3" | "span"
}) {
  return (
    <Component className="mb-2 text-[11px] font-medium text-muted-foreground">
      {children}
    </Component>
  )
}



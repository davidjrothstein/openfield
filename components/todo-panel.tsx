"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { Todo } from "@/hooks/use-todos"
import {
  Circle,
  CheckCircle2,
  Plus,
  X,
  Sparkles,
  ListTodo,
  ChevronDown,
  ChevronUp,
  RotateCcw,
} from "lucide-react"

interface TodoPanelProps {
  view?: string
  manualTodos: Todo[]
  completedTodos: Todo[]
  smartTodos: Todo[]
  dismissedTodos: Todo[]
  onAddManual: (text: string) => void
  onToggle: (id: string) => void
  onRemove: (id: string) => void
  onAcceptSmart: (todo: Todo) => void
  onDismissSmart: (id: string) => void
  onUndismissSmart: (id: string) => void
}

export function TodoPanel({
  view,
  manualTodos,
  completedTodos,
  smartTodos,
  dismissedTodos,
  onAddManual,
  onToggle,
  onRemove,
  onAcceptSmart,
  onDismissSmart,
  onUndismissSmart,
}: TodoPanelProps) {
  const [newTodoText, setNewTodoText] = useState("")
  const [showCompleted, setShowCompleted] = useState(false)
  const [showDismissed, setShowDismissed] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const text = newTodoText.trim()
    if (!text) return
    onAddManual(text)
    setNewTodoText("")
  }

  // Determine header label and icon
  const getHeaderInfo = () => {
    switch (view) {
      case "tasks-priority":
        return { icon: <Zap className="size-3.5 text-muted-foreground" />, label: "Priority Tasks" }
      case "tasks-completed":
        return { icon: <CheckCircle2 className="size-3.5 text-muted-foreground" />, label: "Completed Tasks" }
      case "tasks-dismissed":
        return { icon: <X className="size-3.5 text-muted-foreground" />, label: "Dismissed Suggestions" }
      default:
        return { icon: <ListTodo className="size-3.5 text-muted-foreground" />, label: "Tasks" }
    }
  }

  const headerInfo = getHeaderInfo()
  const showAllSections = !view || view === "tasks-priority"

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border px-5 py-2.5">
        {headerInfo.icon}
        <span className="text-xs font-medium text-foreground">
          {headerInfo.label}
        </span>
        {showAllSections && (
          <span className="ml-auto text-[10px] text-muted-foreground">
            {manualTodos.length + smartTodos.length} pending
          </span>
        )}
        {view === "tasks-completed" && (
          <span className="ml-auto text-[10px] text-muted-foreground">
            {completedTodos.length}
          </span>
        )}
        {view === "tasks-dismissed" && (
          <span className="ml-auto text-[10px] text-muted-foreground">
            {dismissedTodos.length}
          </span>
        )}
      </div>

      {/* Add new (only show in priority/default view) */}
      {showAllSections && (
        <form onSubmit={handleSubmit} className="border-b border-border px-5 py-2.5">
          <div className="flex items-center gap-2">
            <Circle className="size-3.5 shrink-0 text-muted-foreground/30" />
            <input
              type="text"
              value={newTodoText}
              onChange={(e) => setNewTodoText(e.target.value)}
              placeholder="Add a task..."
              className="select-text flex-1 bg-transparent text-[11px] text-foreground placeholder:text-muted-foreground/40 focus:outline-none"
            />
            {newTodoText.trim() && (
              <button
                type="submit"
                className="rounded-md bg-foreground px-2 py-0.5 text-[10px] font-medium text-background transition-colors hover:bg-foreground/80"
              >
                Add
              </button>
            )}
          </div>
        </form>
      )}

      <ScrollArea className="flex-1 overflow-hidden">
        <div className="p-4 space-y-5">

          {/* Your Tasks (only show in priority/default view) */}
          {showAllSections && manualTodos.length > 0 && (
            <section>
              <div className="mb-2 flex items-center gap-1.5 px-1">
                <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
                  Your tasks
                </span>
                <span className="text-[10px] text-muted-foreground/40">
                  {manualTodos.length}
                </span>
              </div>
              <div className="space-y-0.5">
                {manualTodos.map((todo) => (
                  <div
                    key={todo.id}
                    className="group flex items-start gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-muted"
                  >
                    <button
                      onClick={() => onToggle(todo.id)}
                      className="mt-0.5 shrink-0"
                      aria-label="Complete"
                    >
                      <Circle className="size-3.5 text-muted-foreground/40" />
                    </button>
                    <div className="flex-1">
                      <span className="text-[11px] leading-relaxed text-foreground/80">
                        {todo.text}
                      </span>
                      {todo.emailSender && (
                        <p className="text-[10px] text-muted-foreground/40">
                          from {todo.emailSender}
                        </p>
                      )}
                    </div>
                    <button
                      onClick={() => onRemove(todo.id)}
                      className="shrink-0 p-0.5 text-muted-foreground/30 opacity-0 transition-opacity group-hover:opacity-100"
                      aria-label="Remove"
                    >
                      <X className="size-3" />
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Suggested from Emails (Smart Todos) (only show in priority/default view) */}
          {showAllSections && smartTodos.length > 0 && (
            <section>
              <div className="mb-2 flex items-center gap-1.5 px-1">
                <Sparkles className="size-3 text-muted-foreground/40" />
                <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
                  Suggested from emails
                </span>
                <span className="text-[10px] text-muted-foreground/40">
                  {smartTodos.length}
                </span>
              </div>
              <div className="space-y-1">
                {smartTodos.map((todo) => (
                  <div
                    key={todo.id}
                    className="rounded-md border border-dashed border-border/60 px-3 py-2 transition-colors"
                  >
                    <div className="flex items-start gap-2">
                      <Circle className="mt-0.5 size-3.5 shrink-0 text-muted-foreground/30" />
                      <div className="flex-1">
                        <p className="text-[11px] leading-relaxed text-foreground/70">
                          {todo.text}
                        </p>
                        {todo.emailSender && (
                          <p className="mt-0.5 text-[10px] text-muted-foreground/40">
                            from {todo.emailSender}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="mt-1.5 flex gap-1.5 pl-[22px]">
                      <button
                        onClick={() => onDismissSmart(todo.id)}
                        className="flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                      >
                        <X className="size-2.5" />
                        Not relevant
                      </button>
                      <button
                        onClick={() => onAcceptSmart(todo)}
                        className="flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                      >
                        <Plus className="size-2.5" />
                        Add to tasks
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Empty state (only show in priority/default view) */}
          {showAllSections && manualTodos.length === 0 && smartTodos.length === 0 && completedTodos.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-12 text-center">
              <ListTodo className="size-5 text-muted-foreground/30" />
              <p className="text-xs text-muted-foreground">
                All clear
              </p>
              <p className="max-w-[220px] text-[11px] text-muted-foreground/60">
                Add your own tasks above, or suggestions will appear here when emails contain action items
              </p>
            </div>
          )}

          {/* Done (show in all views except dismissed, always expanded in completed view) */}
          {completedTodos.length > 0 && view !== "tasks-dismissed" && (
            <section>
              {view !== "tasks-completed" && (
                <button
                  onClick={() => setShowCompleted(!showCompleted)}
                  className="mb-1.5 flex items-center gap-1.5 px-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/50 transition-colors hover:text-muted-foreground"
                >
                  {showCompleted ? (
                    <ChevronUp className="size-2.5" />
                  ) : (
                    <ChevronDown className="size-2.5" />
                  )}
                  Recently Completed
                  <span className="font-normal normal-case tracking-normal text-muted-foreground/40">
                    {completedTodos.length}
                  </span>
                </button>
              )}
              {(showCompleted || view === "tasks-completed") && (
                <div className="space-y-0.5">
                  {completedTodos.map((todo) => (
                    <div
                      key={todo.id}
                      className="group flex items-start gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-muted"
                    >
                      <button
                        onClick={() => onToggle(todo.id)}
                        className="mt-0.5 shrink-0"
                        aria-label="Mark incomplete"
                      >
                        <CheckCircle2 className="size-3.5 text-muted-foreground/30" />
                      </button>
                      <span className="flex-1 text-[11px] leading-relaxed text-muted-foreground/40 line-through">
                        {todo.text}
                      </span>
                      <button
                        onClick={() => onRemove(todo.id)}
                        className="shrink-0 p-0.5 text-muted-foreground/20 opacity-0 transition-opacity group-hover:opacity-100"
                        aria-label="Remove"
                      >
                        <X className="size-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* Dismissed (show in all views except completed, always expanded in dismissed view) */}
          {dismissedTodos.length > 0 && view !== "tasks-completed" && (
            <section>
              {view !== "tasks-dismissed" && (
                <button
                  onClick={() => setShowDismissed(!showDismissed)}
                  className="mb-1.5 flex items-center gap-1.5 px-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/50 transition-colors hover:text-muted-foreground"
                >
                  {showDismissed ? (
                    <ChevronUp className="size-2.5" />
                  ) : (
                    <ChevronDown className="size-2.5" />
                  )}
                  Dismissed
                  <span className="font-normal normal-case tracking-normal text-muted-foreground/40">
                    {dismissedTodos.length}
                  </span>
                </button>
              )}
              {(showDismissed || view === "tasks-dismissed") && (
                <div className="space-y-0.5">
                  {dismissedTodos.map((todo) => (
                    <div
                      key={todo.id}
                      className="group flex items-start gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-muted"
                    >
                      <X className="mt-0.5 size-3.5 shrink-0 text-muted-foreground/20" />
                      <div className="flex-1">
                        <span className="text-[11px] leading-relaxed text-muted-foreground/40 line-through">
                          {todo.text}
                        </span>
                        {todo.emailSender && (
                          <p className="text-[10px] text-muted-foreground/30">
                            from {todo.emailSender}
                          </p>
                        )}
                      </div>
                      <button
                        onClick={() => onUndismissSmart(todo.id)}
                        className="shrink-0 p-0.5 text-muted-foreground/20 opacity-0 transition-opacity group-hover:opacity-100"
                        aria-label="Restore"
                      >
                        <RotateCcw className="size-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

        </div>
      </ScrollArea>
    </div>
  )
}

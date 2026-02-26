"use client"

import { useState, useEffect, useCallback } from "react"
import { emails } from "@/lib/email-data"
import { FolderNav, type DarkModePreference } from "@/components/folder-nav"
import { EmailList, type Density } from "@/components/email-list"
import { EmailViewer } from "@/components/email-viewer"
import { AiContextPanel } from "@/components/ai-context-panel"
import { FilterModal, type SavedFilter, type FilterCondition } from "@/components/filter-modal"
import { CommandBar } from "@/components/command-bar"
import { TodoPanel } from "@/components/todo-panel"
import { PriorityTasksPanel } from "@/components/priority-tasks-panel"
import { useTodos } from "@/hooks/use-todos"
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"
import { SquarePen, X, Focus, ChevronLeft, ChevronRight, PanelRightClose, PanelRightOpen, Mail } from "lucide-react"
import type { Theme } from "@/components/folder-nav"
import { cn } from "@/lib/utils"

// Sidebar collapse/expand toggle
export default function Page() {
  const [selectedEmailId, setSelectedEmailId] = useState<string | null>("1")
  const [activeFolder, setActiveFolder] = useState("inbox")
  const [commandOpen, setCommandOpen] = useState(false)
  const [pendingDraft, setPendingDraft] = useState<string | null>(null)
  const [replyActive, setReplyActive] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true)
  const [activeView, setActiveView] = useState<string>("mail")
  const [completedTasks, setCompletedTasks] = useState<Set<string>>(new Set())
  const [dismissedTasks, setDismissedTasks] = useState<Set<string>>(new Set())
  const [layoutMode, setLayoutMode] = useState<"vertical" | "horizontal" | "cards">("vertical")
  const [density, setDensity] = useState<Density>("cozy")
  const [viewerHidden, setViewerHidden] = useState(false)
  const [darkMode, setDarkMode] = useState<DarkModePreference>(false)
  const [theme, setTheme] = useState<Theme>("default")
  const [focusMode, setFocusMode] = useState(false)
  const [focusContextCollapsed, setFocusContextCollapsed] = useState(false)
  const [batchMode, setBatchMode] = useState(false)
  const [batchPage, setBatchPage] = useState(0)
  const BATCH_SIZE = 5
  const [showDashboard, setShowDashboard] = useState(false)
  const [savedFilters, setSavedFilters] = useState<SavedFilter[]>([])
  const [filterModalOpen, setFilterModalOpen] = useState(false)
  const [editingFilter, setEditingFilter] = useState<SavedFilter | null>(null)
  const [activeFilterId, setActiveFilterId] = useState<string | null>(null)

  // Live email list — starts with static demo data, replaced by real emails when Gmail is connected
  const [emailList, setEmailList] = useState(emails)
  const [authStatus, setAuthStatus] = useState<{
    authenticated: boolean
    userEmail?: string
    provider?: string
  }>({ authenticated: false })

  // Check auth status on mount
  useEffect(() => {
    fetch("/api/auth/status")
      .then((r) => r.json())
      .then((data) => setAuthStatus(data))
      .catch(() => {/* ignore — falls back to demo data */})
  }, [])

  // Re-fetch emails from the active provider whenever the folder or auth state changes
  useEffect(() => {
    if (!authStatus.authenticated) {
      setEmailList(emails)
      return
    }
    fetch(`/api/emails?folder=${activeFolder}&maxResults=100`)
      .then((r) => r.json())
      .then((data) => { if (data.emails?.length) setEmailList(data.emails) })
      .catch(() => setEmailList(emails))
  }, [authStatus.authenticated, activeFolder])

  const todoSystem = useTodos(emailList)

  // Apply theme + dark classes to <html>
  useEffect(() => {
    const el = document.documentElement
    el.classList.remove("theme-default", "theme-neutral", "theme-forest", "theme-superblue")
    el.classList.add(`theme-${theme}`)

    const applyDark = (isDark: boolean) => el.classList.toggle("dark", isDark)

    if (darkMode === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)")
      applyDark(mq.matches)
      const handler = (e: MediaQueryListEvent) => applyDark(e.matches)
      mq.addEventListener("change", handler)
      return () => mq.removeEventListener("change", handler)
    } else {
      applyDark(darkMode)
    }
  }, [darkMode, theme])

  // Reset viewer when switching layouts
  useEffect(() => {
    setViewerHidden(false)
  }, [layoutMode])

  // 3-state cycle: unchecked -> checked -> dismissed (blank) -> unchecked
  const toggleTask = useCallback((emailId: string) => {
    setCompletedTasks((prev) => {
      const isCompleted = prev.has(emailId)
      if (isCompleted) {
        // completed -> dismissed: remove from completed
        const next = new Set(prev)
        next.delete(emailId)
        return next
      }
      // Check if currently dismissed
      setDismissedTasks((dp) => {
        if (dp.has(emailId)) {
          // dismissed -> unchecked: remove from dismissed
          const next = new Set(dp)
          next.delete(emailId)
          return next
        }
        return dp
      })
      // If not completed and not dismissed: unchecked -> completed
      const next = new Set(prev)
      next.add(emailId)
      return next
    })
  }, [])

  // Separate handler for the completed->dismissed transition
  const handleToggleTask = useCallback((emailId: string) => {
    const isCompleted = completedTasks.has(emailId)
    const isDismissed = dismissedTasks.has(emailId)

    if (!isCompleted && !isDismissed) {
      // unchecked -> completed
      setCompletedTasks((prev) => new Set(prev).add(emailId))
    } else if (isCompleted) {
      // completed -> dismissed (blank)
      setCompletedTasks((prev) => {
        const next = new Set(prev)
        next.delete(emailId)
        return next
      })
      setDismissedTasks((prev) => new Set(prev).add(emailId))
    } else {
      // dismissed -> unchecked
      setDismissedTasks((prev) => {
        const next = new Set(prev)
        next.delete(emailId)
        return next
      })
    }
  }, [completedTasks, dismissedTasks])

  const selectedEmail = emailList.find((e) => e.id === selectedEmailId) ?? null
  const inboxEmails = emailList.filter((e) => e.folder !== "drafts" && e.folder !== "sent")
  const priorityCount = inboxEmails.filter((e) => e.priority).length
  const actionNeededCount = inboxEmails.filter((e) => e.actionRequired).length
  const informationalCount = inboxEmails.filter((e) => !e.actionRequired && !e.priority && !e.isDistributionList).length
  const newslettersCount = inboxEmails.filter((e) => e.isDistributionList).length
  const sentCount = emailList.filter((e) => e.folder === "sent").length
  const draftsCount = emailList.filter((e) => e.folder === "drafts").length

  // All emails with action items (for batch mode)
  const allActionEmails = emailList.filter((e) => e.actions && e.actions.length > 0 && !dismissedTasks.has(e.id))
  const totalActionEmails = allActionEmails.length

  // Batch: current slice of 5
  const batchStart = batchPage * BATCH_SIZE
  const currentBatch = allActionEmails.slice(batchStart, batchStart + BATCH_SIZE)
  const batchActioned = currentBatch.every((e) => completedTasks.has(e.id) || dismissedTasks.has(e.id))
  const hasMoreBatches = batchStart + BATCH_SIZE < allActionEmails.length

  const isInboxEmail = (e: typeof emailList[0]) => e.folder !== "drafts" && e.folder !== "sent"

  const matchesFilter = useCallback((e: typeof emailList[0], conditions: FilterCondition[]) => {
    return conditions.every((c) => {
      switch (c.field) {
        case "status":
          return c.value === "unread" ? !e.read : e.read
        case "sender":
          if (c.value === "internal") return !e.isDistributionList
          return true
        case "attachments":
          return e.attachments.length > 0
        case "action":
          return e.actionRequired
        case "flagged":
          return e.flagged
        case "priority":
          return e.priority
        case "from":
          return e.sender.toLowerCase().includes(c.value.toLowerCase()) || e.senderEmail.toLowerCase().includes(c.value.toLowerCase())
        case "keyword":
          return e.subject.toLowerCase().includes(c.value) || e.preview.toLowerCase().includes(c.value) || e.sender.toLowerCase().includes(c.value)
        default:
          return true
      }
    })
  }, [])

  const activeFilter = savedFilters.find(f => f.id === activeFilterId)

  const filteredEmails = batchMode
    ? currentBatch
    : activeFilter
      ? emailList.filter((e) => isInboxEmail(e) && matchesFilter(e, activeFilter.conditions))
      : emailList.filter((e) => {
          if (activeFolder === "inbox") return isInboxEmail(e)
          if (activeFolder === "priority") return e.priority && isInboxEmail(e)
          if (activeFolder === "action-needed") return e.actionRequired && isInboxEmail(e)
          if (activeFolder === "informational") return isInboxEmail(e) && !e.actionRequired && !e.priority && !e.isDistributionList
          if (activeFolder === "newsletters") return e.isDistributionList && isInboxEmail(e)
          if (activeFolder === "sent") return e.folder === "sent"
          if (activeFolder === "drafts") return e.folder === "drafts"
          return e.folder === activeFolder
        })

  const handleCompose = useCallback(() => {
    // Placeholder -- in production this opens a full compose window
    setCommandOpen(true)
  }, [])

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const mod = e.metaKey || e.ctrlKey

    // Cmd+K -- command palette
    if (mod && e.key === "k") {
      e.preventDefault()
      setCommandOpen((prev) => !prev)
      return
    }

    // Cmd+N -- compose
    if (mod && e.key === "n") {
      e.preventDefault()
      handleCompose()
      return
    }

    // Escape -- close reply (handled in viewer too, but good global fallback)
    if (e.key === "Escape") {
      setCommandOpen(false)
      return
    }

    // Arrow keys -- navigate email list (only when no input is focused)
    const tag = (e.target as HTMLElement)?.tagName
    if (tag === "INPUT" || tag === "TEXTAREA") return

    if (e.key === "ArrowDown" || e.key === "j") {
      e.preventDefault()
      setSelectedEmailId((prev) => {
        const idx = filteredEmails.findIndex((em) => em.id === prev)
        const next = filteredEmails[idx + 1]
        return next ? next.id : prev
      })
      return
    }

    if (e.key === "ArrowUp" || e.key === "k") {
      e.preventDefault()
      setSelectedEmailId((prev) => {
        const idx = filteredEmails.findIndex((em) => em.id === prev)
        const next = filteredEmails[idx - 1]
        return next ? next.id : prev
      })
      return
    }
  }, [filteredEmails, handleCompose])

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [handleKeyDown])

  // Clear pending draft when email changes
  useEffect(() => {
    setPendingDraft(null)
  }, [selectedEmailId])

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-background">
      {/* Focus mode overlays */}
      {focusMode && (
        <>
          {/* Exit button — same center position as the Focus button */}
          <button
            onClick={() => { setFocusMode(false); setFocusContextCollapsed(false) }}
            className="absolute left-1/2 top-0 z-50 flex h-10 -translate-x-1/2 items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] text-muted-foreground/50 transition-colors hover:text-muted-foreground"
            aria-label="Exit focus mode"
          >
            <X className="size-3.5" />
            <span>Exit focus</span>
          </button>

          {/* Prev email — bottom left */}
          {(() => {
            const idx = filteredEmails.findIndex(e => e.id === selectedEmailId)
            const prev = filteredEmails[idx - 1]
            return prev ? (
              <button
                onClick={() => setSelectedEmailId(prev.id)}
                className="absolute bottom-5 left-5 z-50 flex items-center gap-1.5 rounded-full border border-border bg-background/80 px-3 py-1.5 text-[11px] text-muted-foreground shadow-sm backdrop-blur-sm transition-colors hover:bg-muted hover:text-foreground"
                aria-label="Previous email"
              >
                <ChevronLeft className="size-3.5" />
                <span className="max-w-[120px] truncate">{prev.sender.split(" ")[0]}</span>
              </button>
            ) : null
          })()}

          {/* Next email — bottom right */}
          {(() => {
            const idx = filteredEmails.findIndex(e => e.id === selectedEmailId)
            const next = filteredEmails[idx + 1]
            return next ? (
              <button
                onClick={() => setSelectedEmailId(next.id)}
                className="absolute bottom-5 right-5 z-50 flex items-center gap-1.5 rounded-full border border-border bg-background/80 px-3 py-1.5 text-[11px] text-muted-foreground shadow-sm backdrop-blur-sm transition-colors hover:bg-muted hover:text-foreground"
                aria-label="Next email"
              >
                <span className="max-w-[120px] truncate">{next.sender.split(" ")[0]}</span>
                <ChevronRight className="size-3.5" />
              </button>
            ) : null
          })()}

          {/* Re-expand context pane button */}
          {focusContextCollapsed && (
            <button
              onClick={() => setFocusContextCollapsed(false)}
              className="absolute right-3 top-1/2 z-50 -translate-y-1/2 rounded-full border border-border bg-background/80 p-1.5 text-muted-foreground shadow-sm backdrop-blur-sm transition-colors hover:bg-muted hover:text-foreground"
              aria-label="Expand context panel"
            >
              <PanelRightOpen className="size-3.5" />
            </button>
          )}
        </>
      )}
      {/* Title bar (draggable for desktop) — hidden in focus mode */}
      <div className={cn("app-drag-region relative flex h-10 items-center border-b border-border px-4 transition-opacity duration-200", focusMode && "opacity-0 pointer-events-none")}>
        {/* Left */}
        <div className="app-no-drag flex items-center gap-3">
          <span className="text-sm font-medium text-foreground tracking-tight">
            OpenField
          </span>
          <button
            onClick={handleCompose}
            className="flex items-center gap-1.5 rounded-md bg-foreground px-2.5 py-1 text-[11px] font-medium text-background transition-colors hover:bg-foreground/80"
            aria-label="Compose new email"
          >
            <SquarePen className="size-3" />
            <span>Compose</span>
          </button>
        </div>
        {/* Center — Focus button */}
        <div className="app-no-drag absolute left-1/2 -translate-x-1/2">
          <button
            onClick={() => { setFocusMode(true); setFocusContextCollapsed(true) }}
            className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Enter focus mode"
          >
            <Focus className="size-3.5" />
            <span>Focus</span>
          </button>
        </div>
        {/* Right */}
        <div className="app-no-drag ml-auto flex items-center gap-3 text-muted-foreground">
          {authStatus.authenticated ? (
            <span className="flex items-center gap-1.5 text-xs">
              <Mail className="size-3" />
              <span>{authStatus.userEmail}</span>
              <button
                onClick={() =>
                  fetch("/api/auth/logout", { method: "POST" }).then(() =>
                    setAuthStatus({ authenticated: false })
                  )
                }
                className="rounded px-1.5 py-0.5 text-[10px] hover:bg-muted"
                aria-label="Sign out of Gmail"
              >
                Sign out
              </button>
            </span>
          ) : (
            <a
              href="/api/auth/gmail"
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] transition-colors hover:bg-muted hover:text-foreground"
              aria-label="Connect Gmail account"
            >
              <Mail className="size-3.5" />
              <span>Connect Gmail</span>
            </a>
          )}
          <span className="text-xs">
            <CurrentTime />
          </span>
        </div>
      </div>

      {/* Main layout: folder nav | center panels | context pane */}
      <div className="flex h-[calc(100vh-2.5rem)]">
        {/* Folder nav + straddling toggle */}
        <div className="relative flex shrink-0">
          <div
            className="transition-[width,opacity] duration-200 ease-in-out overflow-hidden"
            style={{ width: (focusMode || layoutMode === "cards") ? 0 : sidebarCollapsed ? 56 : 180, opacity: (focusMode || layoutMode === "cards") ? 0 : 1 }}
          >
            <FolderNav
              activeFolder={activeFolder}
              onSelectFolder={(folder) => {
                setActiveFolder(folder)
                setActiveView("mail")
              }}
              onOpenCommand={() => setCommandOpen(true)}
              collapsed={sidebarCollapsed}
              folderCounts={{
                inbox: inboxEmails.length,
                priority: priorityCount,
                "action-needed": actionNeededCount,
                informational: informationalCount,
                newsletters: newslettersCount,
                sent: sentCount,
                drafts: draftsCount,
              }}
              activeView={activeView}
              onSelectView={setActiveView}
              totalTaskCount={todoSystem.totalPending}
              completedTaskCount={todoSystem.completedTodos.length}
              dismissedTaskCount={todoSystem.dismissedTodos.length}
              theme={theme}
              darkMode={darkMode}
              onSetTheme={(t, dark) => {
                const el = document.documentElement
                el.classList.remove("theme-default", "theme-neutral", "theme-forest", "theme-superblue")
                el.classList.add(`theme-${t}`)
                if (dark === "system") {
                  const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches
                  el.classList.toggle("dark", systemDark)
                } else {
                  el.classList.toggle("dark", dark)
                }
                setTheme(t)
                setDarkMode(dark)
              }}
              savedFilters={savedFilters}
              activeFilterId={activeFilterId}
              onCreateFilter={() => { setEditingFilter(null); setFilterModalOpen(true) }}
              onEditFilter={(filter) => { setEditingFilter(filter); setFilterModalOpen(true) }}
              onSelectFilter={(id) => { setActiveFilterId(id === activeFilterId ? null : id); setActiveView("mail") }}
            />
          </div>
          {/* Toggle sits outside overflow-hidden so it's never clipped */}
          {!focusMode && layoutMode !== "cards" && (
            <button
              onClick={() => setSidebarCollapsed((prev) => !prev)}
              className="absolute top-[40px] -right-3 z-20 flex size-6 items-center justify-center rounded border border-border bg-background text-muted-foreground shadow-sm transition-all hover:bg-muted hover:text-foreground"
              aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              <svg className="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                {sidebarCollapsed ? (
                  <polyline points="9 18 15 12 9 6" />
                ) : (
                  <polyline points="15 18 9 12 15 6" />
                )}
              </svg>
            </button>
          )}
        </div>

        {/* Center + Right: resizable horizontal split */}
        {activeView.startsWith("tasks") ? (
          <div className="flex-1">
            <TodoPanel
              view={activeView as "tasks-priority" | "tasks-completed" | "tasks-dismissed"}
              manualTodos={todoSystem.manualTodos}
              completedTodos={todoSystem.completedTodos}
              smartTodos={todoSystem.smartTodos}
              dismissedTodos={todoSystem.dismissedTodos}
              onAddManual={todoSystem.addManualTodo}
              onToggle={todoSystem.toggleTodo}
              onRemove={todoSystem.removeTodo}
              onAcceptSmart={todoSystem.acceptSmartTodo}
              onDismissSmart={todoSystem.dismissSmartTodo}
              onUndismissSmart={todoSystem.undismissSmartTodo}
            />
          </div>
        ) : (
          <ResizablePanelGroup direction="horizontal" className="flex-1">
            {/* Center area: email list (top) + email viewer (bottom) */}
            <ResizablePanel defaultSize={(viewerHidden || layoutMode === "cards") ? 100 : 72} minSize={50}>
              <ResizablePanelGroup
                direction={layoutMode === "vertical" ? "vertical" : "horizontal"}
                key={`${layoutMode}-${viewerHidden}-${focusMode}-${layoutMode === "cards"}`}
              >
                {/* Email list — hidden in focus mode */}
                <ResizablePanel
                  defaultSize={focusMode ? 0 : (viewerHidden || layoutMode === "cards") ? 100 : layoutMode === "vertical" ? 35 : 40}
                  minSize={focusMode ? 0 : layoutMode === "cards" ? 100 : 20}
                  maxSize={focusMode ? 0 : (viewerHidden || layoutMode === "cards") ? 100 : 60}
                  className={focusMode ? "!flex-[0_0_0px] overflow-hidden" : ""}
                >
                  <EmailList
                    emails={filteredEmails}
                    selectedEmailId={selectedEmailId}
                    onSelectEmail={(id) => {
                      setSelectedEmailId(id)
                      if (layoutMode === "cards") {
                        setLayoutMode("vertical")
                      } else if (viewerHidden && layoutMode === "horizontal") {
                        setViewerHidden(false)
                      }
                    }}
                    dimmed={replyActive}
                    activeFolder={activeFolder}
                    filterLabel={activeFilter?.name ?? null}
                    completedTasks={completedTasks}
                    dismissedTasks={dismissedTasks}
                    onToggleTask={handleToggleTask}
                    density={density}
                    onDensityChange={setDensity}
                    layoutMode={layoutMode}
                    onLayoutModeChange={setLayoutMode}
                    batchMode={batchMode}
                    onToggleBatchMode={() => {
                      setBatchMode((prev) => !prev)
                      setBatchPage(0)
                    }}
                    batchActioned={batchActioned}
                    totalActionEmails={totalActionEmails}
                    batchStart={batchStart}
                    batchSize={currentBatch.length}
                    onNextBatch={() => setBatchPage((p) => p + 1)}
                    hasMoreBatches={hasMoreBatches}
                  />
                </ResizablePanel>

                {!viewerHidden && layoutMode !== "cards" && (
                  <>
                    <ResizableHandle
                      className={layoutMode === "vertical" ? "h-px bg-border" : "w-px bg-border"}
                    />

                    {/* Email viewer */}
                    <ResizablePanel
                      defaultSize={layoutMode === "vertical" ? 65 : 60}
                      minSize={30}
                    >
                      <EmailViewer
                        email={selectedEmail}
                        pendingDraft={pendingDraft}
                        onDraftConsumed={() => setPendingDraft(null)}
                        onReplyOpenChange={setReplyActive}
                        showCloseButton={true}
                        onClose={() => setViewerHidden(true)}
                        focusMode={focusMode}
                      />
                    </ResizablePanel>
                  </>
                )}
              </ResizablePanelGroup>
            </ResizablePanel>

            <ResizableHandle className={cn("w-px bg-border", layoutMode === "cards" && "hidden")} />

            {/* Context Pane (right) - shows tasks when viewer is hidden, otherwise AI context */}
            <ResizablePanel
              defaultSize={layoutMode === "cards" ? 0 : 28}
              minSize={(focusMode && focusContextCollapsed) || layoutMode === "cards" ? 0 : 20}
              maxSize={(focusMode && focusContextCollapsed) || layoutMode === "cards" ? 0 : 40}
              className={cn(
                (focusMode && focusContextCollapsed) && "!flex-[0_0_0px] overflow-hidden",
                layoutMode === "cards" && "!flex-[0_0_0px] overflow-hidden"
              )}
            >
              <div className={cn("h-full", theme === "superblue" && "superblue-context")}>
              {showDashboard ? (
                // Dashboard view - all tasks
                <div className="flex h-full flex-col overflow-hidden bg-secondary">
                  <div className="flex items-center gap-2 border-b border-border px-4 py-3">
                    <span className="text-xs font-medium text-foreground">Dashboard</span>
                    <button
                      onClick={() => setShowDashboard(false)}
                      className="ml-auto text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                    >
                      Back to Triage
                    </button>
                  </div>
                  <div className="flex-1 overflow-y-auto px-4 py-3">
                    <div className="space-y-2">
                      {allActionEmails.map((email) => (
                        <button
                          key={email.id}
                          onClick={() => {
                            setSelectedEmailId(email.id)
                            setViewerHidden(false)
                            setShowDashboard(false)
                          }}
                          className="w-full text-left rounded-md p-3 border border-border hover:bg-muted/50 transition-colors group"
                        >
                          <div className="flex items-baseline gap-2 mb-1">
                            <span className="text-[11px] font-medium text-foreground shrink-0">
                              {email.sender.split(" ")[0]}
                            </span>
                            <span className="text-[10px] text-muted-foreground truncate">
                              {email.subject.length > 45
                                ? email.subject.substring(0, 45) + "…"
                                : email.subject}
                            </span>
                          </div>
                          <p className="text-[10px] text-muted-foreground leading-tight line-clamp-2">
                            {email.preview}
                          </p>
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="border-t border-border px-4 py-2 text-[10px] text-muted-foreground text-center">
                    {allActionEmails.length} items total
                  </div>
                </div>
              ) : viewerHidden ? (
                <PriorityTasksPanel
                  emails={allActionEmails}
                  onSelectEmail={(id) => {
                    setSelectedEmailId(id)
                    setViewerHidden(false)
                  }}
                  onShowDashboard={() => setShowDashboard(true)}
                />
              ) : (
                <AiContextPanel
                  email={selectedEmail}
                  onDraftReply={(draft) => setPendingDraft(draft)}
                  onGenerateDraft={(draft) => setPendingDraft(draft)}
                  onShowDashboard={() => setShowDashboard(true)}
                  focusMode={focusMode}
                  onCollapseContext={() => setFocusContextCollapsed(true)}
                  theme={theme}
                />
              )}
              </div>
            </ResizablePanel>
          </ResizablePanelGroup>
        )}
      </div>

      {/* Command Bar */}
      <CommandBar open={commandOpen} onOpenChange={setCommandOpen} />

      {/* Filter Modal */}
      <FilterModal
        open={filterModalOpen}
        onClose={() => { setFilterModalOpen(false); setEditingFilter(null) }}
        editingFilter={editingFilter}
        onSave={(filter) => {
          setSavedFilters((prev) => {
            const idx = prev.findIndex(f => f.id === filter.id)
            if (idx >= 0) {
              const next = [...prev]
              next[idx] = filter
              return next
            }
            return [...prev, filter]
          })
        }}
        onRunOnce={(conditions) => {
          const tempFilter: SavedFilter = {
            id: `temp-${Date.now()}`,
            name: "Run Once",
            query: "",
            conditions,
          }
          setSavedFilters(prev => [...prev, tempFilter])
          setActiveFilterId(tempFilter.id)
          setActiveView("mail")
        }}
        onDelete={(id) => {
          setSavedFilters(prev => prev.filter(f => f.id !== id))
          if (activeFilterId === id) setActiveFilterId(null)
        }}
      />
    </main>
  )
}

function CurrentTime() {
  const [time, setTime] = useState<string | null>(null)

  useEffect(() => {
    const update = () => {
      const now = new Date()
      setTime(
        now.toLocaleTimeString("en-US", {
          hour12: true,
          hour: "numeric",
          minute: "2-digit",
        })
      )
    }
    update()
    const interval = setInterval(update, 1000)
    return () => clearInterval(interval)
  }, [])

  if (!time) return null
  return <>{time}</>
}

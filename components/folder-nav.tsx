"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { folders, belowDividerFolders } from "@/lib/email-data"
import type { SavedFilter } from "@/components/filter-modal"
import {
  Inbox,
  Send,
  FileText,
  Search,
  Settings,
  Zap,
  ListTodo,
  ChevronRight,
  Clock,
  X,
  Palette,
  CircleAlert,
  Info,
  Newspaper,
  ListFilter,
  SlidersHorizontal,
  Plus,
} from "lucide-react"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

export type Theme = "default" | "neutral" | "forest" | "superblue"
export type DarkModePreference = boolean | "system"

const themes: { id: Theme; label: string; light: string; dark: string }[] = [
  { id: "default",   label: "Default",   light: "#f0f3f7", dark: "#0d1117" },
  { id: "neutral",   label: "Neutral",   light: "#f2f2f0", dark: "#1e1e22" },
  { id: "forest",    label: "Forest",    light: "#edf2ea", dark: "#111a12" },
  { id: "superblue", label: "Superblue", light: "#0047ab", dark: "#001a4d" },
]

const folderIcons: Record<string, React.ReactNode> = {
  inbox: <Inbox className="size-4" />,
  priority: <Zap className="size-4" />,
  "action-needed": <CircleAlert className="size-4" />,
  informational: <Info className="size-4" />,
  newsletters: <Newspaper className="size-4" />,
  sent: <Send className="size-4" />,
  drafts: <FileText className="size-4" />,
}

interface FolderNavProps {
  activeFolder: string
  onSelectFolder: (key: string) => void
  onOpenCommand: () => void
  collapsed: boolean
  folderCounts?: Record<string, number>
  activeView: string
  onSelectView: (view: string) => void
  totalTaskCount?: number
  completedTaskCount?: number
  dismissedTaskCount?: number
  theme?: Theme
  darkMode?: DarkModePreference
  onSetTheme?: (theme: Theme, dark: DarkModePreference) => void
  savedFilters?: SavedFilter[]
  activeFilterId?: string | null
  onCreateFilter?: () => void
  onEditFilter?: (filter: SavedFilter) => void
  onSelectFilter?: (filterId: string) => void
}

export function FolderNav({
  activeFolder,
  onSelectFolder,
  onOpenCommand,
  collapsed,
  folderCounts,
  activeView,
  onSelectView,
  totalTaskCount = 0,
  completedTaskCount = 0,
  dismissedTaskCount = 0,
  theme = "default",
  darkMode = false,
  onSetTheme,
  savedFilters = [],
  activeFilterId,
  onCreateFilter,
  onEditFilter,
  onSelectFilter,
}: FolderNavProps) {
  const [tasksExpanded, setTasksExpanded] = useState(true)
  return (
    <div className={cn("flex h-full w-full flex-col border-r border-border bg-secondary py-3", theme === "superblue" && "superblue-sidebar")}>
      {/* Search */}
      <div className={cn("px-2", collapsed ? "flex justify-center" : "")}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={onOpenCommand}
              className={cn(
                "mb-4 flex items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                collapsed
                  ? "size-8 justify-center"
                  : "h-8 w-full gap-2.5 px-2.5"
              )}
              aria-label="Search"
            >
              <Search className="size-4 shrink-0" />
              {!collapsed && (
                <span className="text-xs">Search</span>
              )}
              {!collapsed && (
                <kbd className="ml-auto text-[10px] text-muted-foreground">
                  {"Cmd+K"}
                </kbd>
              )}
            </button>
          </TooltipTrigger>
        </Tooltip>
      </div>

      {/* Divider */}
      <div className={cn("mb-3 h-px bg-border", collapsed ? "mx-auto w-6" : "mx-2")} />

      {/* Folders */}
      <nav className={cn("flex flex-col gap-0.5", collapsed ? "items-center" : "px-2")}>
        {folders.map((folder) => {
          const count = folderCounts?.[folder.key] ?? folder.count
          return (
            <Tooltip key={folder.key}>
              <TooltipTrigger asChild>
                <button
                  onClick={() => onSelectFolder(folder.key)}
                  className={cn(
                    "group relative flex items-center rounded-md transition-colors",
                    collapsed
                      ? "size-8 justify-center"
                      : "h-8 w-full gap-2.5 px-2.5",
                    activeFolder === folder.key
                      ? "bg-muted text-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                  aria-label={folder.name}
                >
                  <span className="shrink-0">{folderIcons[folder.key]}</span>
                  {!collapsed && (
                    <span className="text-xs">{folder.name}</span>
                  )}
                  {count > 0 && !collapsed && (
                    <span className="ml-auto text-[10px] text-muted-foreground">
                      {count}
                    </span>
                  )}
                </button>
              </TooltipTrigger>
            </Tooltip>
          )
        })}

        {/* Filters section */}
        <div className={cn("mt-1 flex flex-col gap-0.5", collapsed && "items-center")}>
          {/* Persistent "Create a Filter" action row */}
          <button
            onClick={() => onCreateFilter?.()}
            className={cn(
              "flex items-center rounded-md text-muted-foreground/50 transition-colors hover:text-muted-foreground",
              collapsed ? "size-7 justify-center" : "h-7 w-full gap-2 px-2.5 text-[11px]"
            )}
            aria-label="Create a Filter"
          >
            <Plus className="size-3 shrink-0" />
            {!collapsed && <span>Create a Filter</span>}
          </button>

          {/* Saved filters */}
          {savedFilters.map((filter) => (
            <div key={filter.id} className={cn("group/filter relative", collapsed && "flex justify-center")}>
              <button
                onClick={() => onSelectFilter?.(filter.id)}
                className={cn(
                  "flex items-center rounded-md transition-colors",
                  collapsed
                    ? "size-7 justify-center"
                    : "h-7 w-full gap-2 px-2.5 text-xs",
                  activeFilterId === filter.id
                    ? "bg-muted/60 text-foreground"
                    : "text-muted-foreground hover:bg-muted/40 hover:text-foreground"
                )}
                aria-label={filter.name}
              >
                <ListFilter className="size-3 shrink-0" />
                {!collapsed && <span className="truncate">{filter.name}</span>}
              </button>
              {!collapsed && (
                <button
                  onClick={(e) => { e.stopPropagation(); onEditFilter?.(filter) }}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground/0 transition-all group-hover/filter:text-muted-foreground hover:!bg-muted hover:!text-foreground"
                  aria-label={`Edit filter ${filter.name}`}
                >
                  <SlidersHorizontal className="size-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      </nav>

      {/* Divider */}
      <div className={cn("my-3 h-px bg-border", collapsed ? "mx-auto w-6" : "mx-2")} />

      {/* Below-divider folders (Sent) */}
      <nav className={cn("flex flex-col gap-0.5", collapsed ? "items-center" : "px-2")}>
        {belowDividerFolders.map((folder) => {
          const count = folderCounts?.[folder.key] ?? folder.count
          return (
            <Tooltip key={folder.key}>
              <TooltipTrigger asChild>
                <button
                  onClick={() => onSelectFolder(folder.key)}
                  className={cn(
                    "relative flex items-center rounded-md transition-colors",
                    collapsed
                      ? "size-8 justify-center"
                      : "h-8 w-full gap-2.5 px-2.5",
                    activeFolder === folder.key
                      ? "bg-muted text-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                  aria-label={folder.name}
                >
                  <span className="shrink-0">{folderIcons[folder.key]}</span>
                  {!collapsed && (
                    <span className="text-xs">{folder.name}</span>
                  )}
                  {count > 0 && !collapsed && (
                    <span className="ml-auto text-[10px] text-muted-foreground">
                      {count}
                    </span>
                  )}
                </button>
              </TooltipTrigger>
            </Tooltip>
          )
        })}
      </nav>

      {/* Divider */}
      <div className={cn("my-3 h-px bg-border", collapsed ? "mx-auto w-6" : "mx-2")} />

      {/* Tasks (expandable parent) */}
      <nav className={cn("flex flex-col gap-0.5", collapsed ? "items-center" : "px-2")}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={() => {
                if (collapsed) {
                  onSelectView("tasks")
                } else {
                  setTasksExpanded(!tasksExpanded)
                }
              }}
              className={cn(
                "relative flex items-center rounded-md transition-colors",
                collapsed
                  ? "size-8 justify-center"
                  : "h-8 w-full gap-2.5 px-2.5",
                activeView.startsWith("tasks")
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
              aria-label="Tasks"
            >
              {!collapsed && (
                <ChevronRight className={cn("size-3 shrink-0 transition-transform", tasksExpanded && "rotate-90")} />
              )}
              <ListTodo className="size-4 shrink-0" />
              {!collapsed && (
                <span className="text-xs">Tasks</span>
              )}
              {totalTaskCount > 0 && !collapsed && (
                <span className="ml-auto text-[10px] text-muted-foreground">
                  {totalTaskCount}
                </span>
              )}
            </button>
          </TooltipTrigger>
        </Tooltip>

        {/* Nested task views - expanded sidebar */}
        {!collapsed && tasksExpanded && (
          <div className="flex flex-col gap-0.5 pl-3">
            {/* Priority Tasks */}
            <button
              onClick={() => onSelectView("tasks-priority")}
              className={cn(
                "flex h-7 items-center gap-2 rounded-md px-2.5 text-xs transition-colors",
                activeView === "tasks-priority"
                  ? "bg-muted/60 text-foreground"
                  : "text-muted-foreground hover:bg-muted/40 hover:text-foreground"
              )}
            >
              <Zap className="size-3 shrink-0" />
              <span>Priority</span>
              {totalTaskCount > 0 && (
                <span className="ml-auto text-[10px] text-muted-foreground/60">
                  {totalTaskCount}
                </span>
              )}
            </button>

            {/* Recently Completed */}
            <button
              onClick={() => onSelectView("tasks-completed")}
              className={cn(
                "flex h-7 items-center gap-2 rounded-md px-2.5 text-xs transition-colors",
                activeView === "tasks-completed"
                  ? "bg-muted/60 text-foreground"
                  : "text-muted-foreground hover:bg-muted/40 hover:text-foreground"
              )}
            >
              <Clock className="size-3 shrink-0" />
              <span>Completed</span>
              {completedTaskCount > 0 && (
                <span className="ml-auto text-[10px] text-muted-foreground/60">
                  {completedTaskCount}
                </span>
              )}
            </button>

            {/* Dismissed */}
            <button
              onClick={() => onSelectView("tasks-dismissed")}
              className={cn(
                "flex h-7 items-center gap-2 rounded-md px-2.5 text-xs transition-colors",
                activeView === "tasks-dismissed"
                  ? "bg-muted/60 text-foreground"
                  : "text-muted-foreground hover:bg-muted/40 hover:text-foreground"
              )}
            >
              <X className="size-3 shrink-0" />
              <span>Dismissed</span>
              {dismissedTaskCount > 0 && (
                <span className="ml-auto text-[10px] text-muted-foreground/60">
                  {dismissedTaskCount}
                </span>
              )}
            </button>
          </div>
        )}

        {/* Nested task views - collapsed sidebar (icon-only) */}
        {collapsed && (
          <div className="flex flex-col gap-0.5 items-center">
            <button
              onClick={() => onSelectView("tasks-priority")}
              className={cn(
                "flex size-7 items-center justify-center rounded-md transition-colors",
                activeView === "tasks-priority"
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
              aria-label="Priority Tasks"
            >
              <Zap className="size-3.5" />
            </button>
            <button
              onClick={() => onSelectView("tasks-completed")}
              className={cn(
                "flex size-7 items-center justify-center rounded-md transition-colors",
                activeView === "tasks-completed"
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
              aria-label="Completed Tasks"
            >
              <Clock className="size-3.5" />
            </button>
            <button
              onClick={() => onSelectView("tasks-dismissed")}
              className={cn(
                "flex size-7 items-center justify-center rounded-md transition-colors",
                activeView === "tasks-dismissed"
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
              aria-label="Dismissed Tasks"
            >
              <X className="size-3.5" />
            </button>
          </div>
        )}
      </nav>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Theme + Settings */}
      <div className={cn("flex flex-col gap-0.5", collapsed ? "items-center" : "px-2")}>

        <Popover>
          <PopoverTrigger asChild>
            <button
              className={cn(
                "flex items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                collapsed ? "size-8 justify-center" : "h-8 w-full gap-2.5 px-2.5"
              )}
              aria-label="Theme"
            >
              <Palette className="size-4 shrink-0" />
              {!collapsed && <span className="text-xs">Theme</span>}
            </button>
          </PopoverTrigger>
          <PopoverContent side="right" align="end" className="w-48 p-3">
            <p className="mb-2 text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Theme</p>
            <div className="flex flex-col gap-2">
              {themes.map((t) => (
                <div key={t.id}>
                  <p className="mb-1 text-[10px] text-muted-foreground">{t.label}</p>
                  <div className="flex gap-1.5">
                    {/* Light swatch */}
                    <button
                      onClick={() => onSetTheme?.(t.id, false)}
                      className={cn(
                        "flex h-7 w-7 items-center justify-center rounded-md border-2 transition-all",
                        theme === t.id && darkMode === false ? "border-foreground" : "border-transparent hover:border-border"
                      )}
                      style={{ background: t.light }}
                      aria-label={`${t.label} light`}
                    >
                      {theme === t.id && darkMode === false && (
                        <div className="size-1.5 rounded-full bg-foreground" />
                      )}
                    </button>
                    {/* System swatch — diagonal half light / half dark */}
                    <button
                      onClick={() => onSetTheme?.(t.id, "system")}
                      className={cn(
                        "relative flex h-7 w-7 items-center justify-center overflow-hidden rounded-md border-2 transition-all",
                        theme === t.id && darkMode === "system" ? "border-foreground" : "border-transparent hover:border-border"
                      )}
                      aria-label={`${t.label} system`}
                    >
                      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 28 28" preserveAspectRatio="none">
                        <polygon points="0,0 28,0 0,28" fill={t.light} />
                        <polygon points="28,0 28,28 0,28" fill={t.dark} />
                      </svg>
                      {theme === t.id && darkMode === "system" && (
                        <div className="relative z-10 size-1.5 rounded-full bg-foreground" />
                      )}
                    </button>
                    {/* Dark swatch */}
                    <button
                      onClick={() => onSetTheme?.(t.id, true)}
                      className={cn(
                        "flex h-7 w-7 items-center justify-center rounded-md border-2 transition-all",
                        theme === t.id && darkMode === true ? "border-white" : "border-transparent hover:border-border"
                      )}
                      style={{ background: t.dark }}
                      aria-label={`${t.label} dark`}
                    >
                      {theme === t.id && darkMode === true && (
                        <div className="size-1.5 rounded-full bg-white" />
                      )}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </PopoverContent>
        </Popover>

        <button
          className={cn(
            "flex items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
            collapsed ? "size-8 justify-center" : "h-8 w-full gap-2.5 px-2.5"
          )}
          aria-label="Settings"
        >
          <Settings className="size-4 shrink-0" />
          {!collapsed && <span className="text-xs">Settings</span>}
        </button>
      </div>
    </div>
  )
}

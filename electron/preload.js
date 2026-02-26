/**
 * Electron preload script
 *
 * Runs in the renderer process before the web page loads.
 * Exposes a minimal, carefully scoped API to the renderer via contextBridge.
 * Node.js and Electron internals are NOT accessible from the renderer —
 * only what is explicitly whitelisted here.
 *
 * The web app checks window.electron?.isElectron to opt into any
 * desktop-specific behaviour (e.g. native title bar drag regions).
 */

const { contextBridge } = require('electron')

contextBridge.exposeInMainWorld('electron', {
  /** True when running inside Electron (vs. a browser). */
  isElectron: true,
  /** Host OS — useful for platform-specific keyboard shortcut labels. */
  platform: process.platform,
})

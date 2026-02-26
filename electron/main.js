/**
 * OpenField — Electron main process
 *
 * Wraps the Next.js web app in a native desktop window.
 * The web app runs unchanged — this file only handles window management,
 * OS-level concerns, and (optionally) the Next.js server lifecycle in
 * production builds.
 *
 * Dev:        next dev runs separately; Electron loads http://localhost:3000
 * Production: Next.js is started as a child process on a random port, then
 *             the window is pointed at http://localhost:<port>
 */

const { app, BrowserWindow, shell, Menu } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')

const isDev = process.env.NODE_ENV !== 'production'
const DEV_URL = 'http://localhost:3000'

let mainWindow = null
let nextServer = null

// ---------------------------------------------------------------------------
// Window creation
// ---------------------------------------------------------------------------

function createWindow(url) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 600,
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      // Credentials (cookies) must work for the OAuth flow
      partition: 'persist:openfield',
    },
  })

  mainWindow.loadURL(url)

  // Open all external links in the system browser, not in Electron
  mainWindow.webContents.setWindowOpenHandler(({ url: targetUrl }) => {
    if (!targetUrl.startsWith('http://localhost')) {
      shell.openExternal(targetUrl)
      return { action: 'deny' }
    }
    return { action: 'allow' }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// ---------------------------------------------------------------------------
// Production: start the Next.js server as a child process
// ---------------------------------------------------------------------------

function findFreePort(start = 3100) {
  return new Promise((resolve, reject) => {
    const server = http.createServer()
    server.listen(start, () => {
      const { port } = server.address()
      server.close(() => resolve(port))
    })
    server.on('error', () => findFreePort(start + 1).then(resolve).catch(reject))
  })
}

function waitForServer(url, maxAttempts = 30, interval = 500) {
  return new Promise((resolve, reject) => {
    let attempts = 0
    const check = () => {
      http.get(url, (res) => {
        if (res.statusCode < 500) return resolve()
        retry()
      }).on('error', retry)
    }
    const retry = () => {
      if (++attempts >= maxAttempts) return reject(new Error(`Server at ${url} did not start`))
      setTimeout(check, interval)
    }
    check()
  })
}

async function startNextServer() {
  const port = await findFreePort()
  const appDir = path.join(__dirname, '..')

  nextServer = spawn(
    process.execPath,
    [path.join(appDir, 'node_modules', '.bin', 'next'), 'start', '--port', String(port)],
    {
      cwd: appDir,
      env: { ...process.env, PORT: String(port) },
      stdio: 'pipe',
    }
  )

  nextServer.stdout.on('data', (d) => process.stdout.write(d))
  nextServer.stderr.on('data', (d) => process.stderr.write(d))
  nextServer.on('error', (err) => console.error('[next server]', err))

  const serverUrl = `http://localhost:${port}`
  await waitForServer(serverUrl)
  return serverUrl
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
  let appUrl = DEV_URL

  if (!isDev) {
    try {
      appUrl = await startNextServer()
    } catch (err) {
      console.error('Failed to start Next.js server:', err)
      app.quit()
      return
    }
  }

  createWindow(appUrl)

  // macOS: re-open window when dock icon is clicked
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow(appUrl)
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  if (nextServer) {
    nextServer.kill()
    nextServer = null
  }
})

// ---------------------------------------------------------------------------
// macOS application menu
// ---------------------------------------------------------------------------

if (process.platform === 'darwin') {
  app.on('ready', () => {
    const template = [
      {
        label: app.name,
        submenu: [
          { role: 'about' },
          { type: 'separator' },
          { role: 'services' },
          { type: 'separator' },
          { role: 'hide' },
          { role: 'hideOthers' },
          { role: 'unhide' },
          { type: 'separator' },
          { role: 'quit' },
        ],
      },
      {
        label: 'Edit',
        submenu: [
          { role: 'undo' },
          { role: 'redo' },
          { type: 'separator' },
          { role: 'cut' },
          { role: 'copy' },
          { role: 'paste' },
          { role: 'selectAll' },
        ],
      },
      {
        label: 'View',
        submenu: [
          { role: 'reload' },
          { role: 'toggleDevTools' },
          { type: 'separator' },
          { role: 'resetZoom' },
          { role: 'zoomIn' },
          { role: 'zoomOut' },
          { type: 'separator' },
          { role: 'togglefullscreen' },
        ],
      },
      {
        label: 'Window',
        submenu: [
          { role: 'minimize' },
          { role: 'zoom' },
          { type: 'separator' },
          { role: 'front' },
        ],
      },
    ]
    Menu.setApplicationMenu(Menu.buildFromTemplate(template))
  })
}

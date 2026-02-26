/**
 * Mock provider — serves the static sample emails from lib/email-data.ts.
 *
 * Used when no real provider is authenticated, so the UI always has data
 * to display in development and in the browser demo.
 *
 * The mock provider has no auth flow; isAuthenticated() always returns true.
 */

import { emails as sampleEmails } from '../lib/email-data'
import {
  EmailProvider,
  EmailMessage,
  Folder,
  SendEmailOptions,
  QueryOptions,
  AuthOptions,
  AuthTokens,
  registerProvider,
} from './index'

const FOLDERS: Folder[] = [
  { id: 'inbox', name: 'inbox', displayName: 'Inbox' },
  { id: 'priority', name: 'priority', displayName: 'Priority' },
  { id: 'action-needed', name: 'action-needed', displayName: 'Action Needed' },
  { id: 'informational', name: 'informational', displayName: 'Informational' },
  { id: 'newsletters', name: 'newsletters', displayName: 'Newsletters' },
  { id: 'sent', name: 'sent', displayName: 'Sent' },
  { id: 'drafts', name: 'drafts', displayName: 'Drafts' },
]

const mockProvider: EmailProvider = {
  name: 'mock',
  displayName: 'Demo (Mock)',

  getAuthUrl(_options?: AuthOptions): string {
    // No real OAuth for the mock provider
    return '/'
  },

  async exchangeCodeForTokens(_code: string, _redirectUri: string): Promise<AuthTokens> {
    return { provider: 'mock', accessToken: 'mock', userEmail: 'demo@openfield.app' }
  },

  async refreshTokens(tokens: AuthTokens): Promise<AuthTokens> {
    return tokens
  },

  async isAuthenticated(_tokens: AuthTokens): Promise<boolean> {
    return true
  },

  async getFolders(_tokens: AuthTokens): Promise<Folder[]> {
    return FOLDERS
  },

  async getEmails(
    _tokens: AuthTokens,
    folder?: string,
    options: QueryOptions = {}
  ): Promise<EmailMessage[]> {
    let result = sampleEmails as EmailMessage[]

    if (folder && folder !== 'all') {
      if (folder === 'priority') {
        result = result.filter((e) => e.priority)
      } else if (folder === 'action-needed') {
        result = result.filter((e) => e.actionRequired)
      } else if (folder === 'informational') {
        result = result.filter((e) => !e.priority && !e.actionRequired && e.folder === 'inbox')
      } else {
        result = result.filter((e) => e.folder === folder)
      }
    }

    if (options.maxResults) {
      result = result.slice(0, options.maxResults)
    }

    return result
  },

  async getEmail(_tokens: AuthTokens, id: string): Promise<EmailMessage> {
    const email = (sampleEmails as EmailMessage[]).find((e) => e.id === id)
    if (!email) throw new Error(`Mock: email ${id} not found`)
    return email
  },

  async sendEmail(_tokens: AuthTokens, _email: SendEmailOptions): Promise<void> {
    // No-op in mock provider
    console.log('[mock provider] sendEmail called — no-op in demo mode')
  },

  async markAsRead(_tokens: AuthTokens, _ids: string[]): Promise<void> {},
  async markAsUnread(_tokens: AuthTokens, _ids: string[]): Promise<void> {},
  async archiveEmails(_tokens: AuthTokens, _ids: string[]): Promise<void> {},
  async deleteEmails(_tokens: AuthTokens, _ids: string[]): Promise<void> {},
}

registerProvider(mockProvider)
export default mockProvider

/**
 * Secure token storage for OpenField.
 *
 * Tokens are AES-256-GCM encrypted and stored in an HTTP-only, Secure cookie.
 * They are never written to localStorage or exposed to client-side JavaScript.
 *
 * Required environment variable:
 *   OPENFIELD_TOKEN_SECRET — a 32-character (or longer) secret key
 *   Generate one with:  openssl rand -hex 32
 */

import { createCipheriv, createDecipheriv, randomBytes } from 'crypto'
import { cookies } from 'next/headers'
import type { AuthTokens } from '@/providers/index'

const COOKIE_NAME = 'openfield_session'
const ALGORITHM = 'aes-256-gcm'
const COOKIE_MAX_AGE = 60 * 60 * 24 * 30 // 30 days

function getEncryptionKey(): Buffer {
  const secret = process.env.OPENFIELD_TOKEN_SECRET
  if (!secret) {
    throw new Error(
      'OPENFIELD_TOKEN_SECRET is not set. ' +
        'Generate one with: openssl rand -hex 32'
    )
  }
  // Pad/truncate to exactly 32 bytes for AES-256
  return Buffer.from(secret.padEnd(32, '0').slice(0, 32), 'utf-8')
}

/** Encrypts a token bundle to a URL-safe string. */
export function encryptTokens(tokens: AuthTokens): string {
  const key = getEncryptionKey()
  const iv = randomBytes(16)
  const cipher = createCipheriv(ALGORITHM, key, iv)
  const plaintext = JSON.stringify(tokens)
  const encrypted = Buffer.concat([
    cipher.update(plaintext, 'utf-8'),
    cipher.final(),
  ])
  const authTag = cipher.getAuthTag()
  // Format: <iv_hex>.<authTag_hex>.<ciphertext_hex>
  return [iv.toString('hex'), authTag.toString('hex'), encrypted.toString('hex')].join('.')
}

/** Decrypts an encrypted token string. Throws if tampered. */
export function decryptTokens(encrypted: string): AuthTokens {
  const key = getEncryptionKey()
  const parts = encrypted.split('.')
  if (parts.length !== 3) throw new Error('Invalid token format')
  const [ivHex, authTagHex, dataHex] = parts
  const iv = Buffer.from(ivHex, 'hex')
  const authTag = Buffer.from(authTagHex, 'hex')
  const data = Buffer.from(dataHex, 'hex')
  const decipher = createDecipheriv(ALGORITHM, key, iv)
  decipher.setAuthTag(authTag)
  const decrypted = Buffer.concat([decipher.update(data), decipher.final()])
  return JSON.parse(decrypted.toString('utf-8')) as AuthTokens
}

/** Reads and decrypts tokens from the session cookie. Returns null if missing or invalid. */
export async function getStoredTokens(): Promise<AuthTokens | null> {
  const cookieStore = await cookies()
  const session = cookieStore.get(COOKIE_NAME)
  if (!session?.value) return null
  try {
    return decryptTokens(session.value)
  } catch {
    return null
  }
}

/** Encrypts and stores tokens in an HTTP-only session cookie. */
export async function storeTokens(tokens: AuthTokens): Promise<void> {
  const cookieStore = await cookies()
  const encrypted = encryptTokens(tokens)
  cookieStore.set(COOKIE_NAME, encrypted, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: COOKIE_MAX_AGE,
    path: '/',
  })
}

/** Removes the session cookie, effectively signing the user out. */
export async function clearTokens(): Promise<void> {
  const cookieStore = await cookies()
  cookieStore.delete(COOKIE_NAME)
}

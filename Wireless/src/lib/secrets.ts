import "server-only";
import { createCipheriv, createDecipheriv, randomBytes, createHash } from "node:crypto";

/**
 * Credential encryption for the integrations table (AES-256-GCM).
 *
 * Vendor API credentials are stored in Postgres as `{ enc: "<blob>" }` where
 * the blob is iv:authTag:ciphertext (base64url). The key comes from the
 * CREDENTIALS_ENCRYPTION_KEY env var (any strong passphrase; it is SHA-256
 * hashed to a 32-byte key). Without the env var, encryption is unavailable and
 * credential writes are refused — secrets are never silently stored plaintext.
 */

const ENC_FIELD = "enc";

function key(): Buffer | null {
  const raw = process.env.CREDENTIALS_ENCRYPTION_KEY;
  if (!raw) return null;
  // Normalize any-length passphrase to exactly 32 bytes for AES-256.
  return createHash("sha256").update(raw).digest();
}

export function encryptionAvailable(): boolean {
  return key() !== null;
}

/** Encrypt a credentials object into the storable `{ enc }` envelope. */
export function encryptCredentials(creds: Record<string, string>): Record<string, string> {
  const k = key();
  if (!k) {
    throw new Error(
      "CREDENTIALS_ENCRYPTION_KEY is not set — refusing to store credentials unencrypted."
    );
  }
  const iv = randomBytes(12); // GCM standard 96-bit nonce
  const cipher = createCipheriv("aes-256-gcm", k, iv);
  const plaintext = Buffer.from(JSON.stringify(creds), "utf8");
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const tag = cipher.getAuthTag();
  const blob = [iv, tag, ciphertext].map((b) => b.toString("base64url")).join(":");
  return { [ENC_FIELD]: blob };
}

/**
 * Decrypt a stored credentials envelope. Returns null when the row has no
 * credentials, the envelope is malformed, or the key is missing/wrong —
 * callers treat null as "not configured" and fall back to mock mode.
 */
export function decryptCredentials(
  stored: Record<string, string> | null
): Record<string, string> | null {
  if (!stored?.[ENC_FIELD]) return null;
  const k = key();
  if (!k) return null;
  try {
    const [ivB64, tagB64, dataB64] = stored[ENC_FIELD].split(":");
    const iv = Buffer.from(ivB64, "base64url");
    const tag = Buffer.from(tagB64, "base64url");
    const data = Buffer.from(dataB64, "base64url");
    const decipher = createDecipheriv("aes-256-gcm", k, iv);
    decipher.setAuthTag(tag);
    const plain = Buffer.concat([decipher.update(data), decipher.final()]);
    return JSON.parse(plain.toString("utf8"));
  } catch {
    // Tampered blob or wrong key — treat as unconfigured rather than crash.
    return null;
  }
}

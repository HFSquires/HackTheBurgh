// Firestore through the Admin SDK, server-side only. The browser never talks to the database: firestore.rules
// deny all client access, and every read/write goes through /api/profile after the Auth0 token is verified.
import { initializeApp, cert, getApps } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";

export function db() {
  if (!getApps().length) {
    const raw = process.env.FIREBASE_SERVICE_ACCOUNT;
    if (!raw) throw new Error("Server not configured: set FIREBASE_SERVICE_ACCOUNT");
    initializeApp({ credential: cert(JSON.parse(raw)) });
  }
  return getFirestore();
}

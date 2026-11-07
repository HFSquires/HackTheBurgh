// GET    /api/profile  -> the signed-in user's saved account (or an empty one)
// PUT    /api/profile  -> replace it (validated: no card numbers, known fields only)
// DELETE /api/profile  -> delete everything we hold for this user
// Auth: "Authorization: Bearer <Auth0 ID token>" from the web page or the extension.
import { verifyUser, userDocId } from "../lib/auth.js";
import { db } from "../lib/firestore.js";
import { cleanAccount, emptyAccount } from "../lib/validate.js";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  let user;
  try {
    user = await verifyUser(req.headers.authorization);
  } catch (e) {
    const notConfigured = /not configured/.test(e.message);
    return res.status(notConfigured ? 500 : 401).json({ error: notConfigured ? e.message : "Please sign in again." });
  }

  try {
    const ref = db().collection("users").doc(userDocId(user.sub));

    if (req.method === "GET") {
      const snap = await ref.get();
      return res.status(200).json({ ...emptyAccount(), ...(snap.exists ? snap.data().account : {}), email: user.email || null });
    }

    if (req.method === "PUT") {
      const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body;
      const { account, error } = cleanAccount(body);
      if (error) return res.status(400).json({ error });
      const updatedAt = new Date().toISOString();
      await ref.set({ account: { ...account, updatedAt }, authSub: user.sub, updatedAt });
      return res.status(200).json({ ...account, updatedAt, email: user.email || null });
    }

    if (req.method === "DELETE") {
      await ref.delete();
      return res.status(200).json({ deleted: true });
    }

    res.setHeader("Allow", "GET, PUT, DELETE");
    return res.status(405).json({ error: "Method not allowed" });
  } catch (e) {
    console.error("profile api error", e);
    return res.status(500).json({ error: "Something went wrong saving your details. Please try again." });
  }
}

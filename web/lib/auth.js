// Checks the Auth0 ID token sent as "Authorization: Bearer <token>" (from the web page or the extension) and
// returns its claims. Signature, issuer, audience and expiry are all verified against Auth0's published keys.
import { createRemoteJWKSet, jwtVerify } from "jose";

let jwks;

export async function verifyUser(authorization) {
  const domain = process.env.AUTH0_DOMAIN;
  const clientId = process.env.AUTH0_CLIENT_ID;
  if (!domain || !clientId) throw new Error("Server not configured: set AUTH0_DOMAIN and AUTH0_CLIENT_ID");

  const token = /^Bearer\s+(.+)$/i.exec(authorization || "")?.[1];
  if (!token) throw new Error("Missing sign-in token");

  jwks ||= createRemoteJWKSet(new URL(`https://${domain}/.well-known/jwks.json`));
  const { payload } = await jwtVerify(token, jwks, { issuer: `https://${domain}/`, audience: clientId });
  if (!payload.sub) throw new Error("Token has no user");
  return payload;
}

// Firestore document id for a user. Auth0 ids look like "auth0|abc" or "google-oauth2|123"; "/" isn't allowed.
export const userDocId = (sub) => sub.replace(/\//g, "_");

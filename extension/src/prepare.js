// Works out the fastest route to checkout on another store, from a product URL.
// The link carries the basket only. Personal details are typed in on the page (handoff.js), never put in a URL,
// where they'd end up in browser history and the store's logs/analytics.
globalThis.ST = globalThis.ST || {};

(() => {
  const get = (url) => fetch(url, { credentials: "omit", redirect: "follow" });

  const escapeRe = (t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  // Shopify variant from what the shopper chose, e.g. "Forest · M" matches option1 "Forest" + option2 "M".
  // Only returns a variant we're sure of; otherwise the shopper (or the AI fallback) picks on the page.
  function pickVariant(variants, wantedVariant, urlVariant) {
    if (urlVariant) return variants.find((v) => String(v.id) === urlVariant) || null;
    if (variants.length === 1) return variants[0];
    const want = (wantedVariant || "").toLowerCase();
    if (!want) return null;
    const hits = variants.filter((v) =>
      [v.option1, v.option2, v.option3]
        .filter(Boolean)
        .every((o) => new RegExp(`(^|[^a-z0-9])${escapeRe(o.toLowerCase())}([^a-z0-9]|$)`).test(want))
    );
    return hits.length === 1 ? hits[0] : null;
  }

  async function checkoutUrlFor(raw, wanted = {}) {
    const qty = Math.max(1, Number(wanted.qty) || 1);
    const u = new URL(raw);

    // Already a basket link.
    if (/\/cart\/\d+:\d+/.test(u.pathname) || /\/gp\/aws\/cart\/add/.test(u.pathname) || u.searchParams.has("add-to-cart")) {
      return { url: raw, method: "cart-link" };
    }

    // Amazon: product ID from the URL -> add-to-basket link.
    if (/(^|\.)amazon\./.test(u.hostname)) {
      const asin = (u.pathname.match(/\/(?:dp|gp\/product|gp\/aw\/d)\/([A-Z0-9]{10})/i) || [])[1];
      // A link to one particular seller's offer (m= / smid=): a basket link would add Amazon's default offer at a
      // different price (or nothing), so go via the product page.
      if (asin && (u.searchParams.has("m") || u.searchParams.has("smid"))) {
        ST.log("prepare: Amazon link is for a specific seller, using the product page", { seller: u.searchParams.get("m") || u.searchParams.get("smid") });
        return { url: raw, method: "product-page" };
      }
      if (asin) return { url: `${u.origin}/gp/aws/cart/add.html?ASIN.1=${asin}&Quantity.1=${qty}`, method: "amazon-cart" };
    }

    // Shopify: every store exposes /products/<handle>.js; a /cart/<variant>:<qty> link opens checkout directly.
    const handle = (u.pathname.match(/\/products\/([^/?#]+)/) || [])[1];
    if (handle) {
      const res = await get(`${u.origin}/products/${handle}.js`).catch(() => null);
      if (res?.ok) {
        const product = await res.json().catch(() => null);
        const variants = product?.variants || [];
        const v = pickVariant(variants, wanted.variant, u.searchParams.get("variant"));
        if (v && v.available !== false) return { url: `${u.origin}/cart/${v.id}:${qty}`, method: "shopify-cart" };
        if (variants.length) return { url: raw, method: "product-page" };
      }
    }

    // WooCommerce: simple products have an add-to-cart id; ?add-to-cart= on /checkout adds it and opens checkout.
    const html = await get(raw).then((r) => (r.ok ? r.text() : "")).catch(() => "");
    if (/woocommerce/i.test(html)) {
      const id = (html.match(/name=["']add-to-cart["'][^>]*value=["'](\d+)/i) || html.match(/value=["'](\d+)["'][^>]*name=["']add-to-cart["']/i) || [])[1];
      if (id) return { url: `${u.origin}/checkout/?add-to-cart=${id}&quantity=${qty}`, method: "woocommerce-cart" };
    }

    return { url: raw, method: "product-page" };
  }

  // Builds the route, saves the hand-off for the destination page, opens it in a new tab.
  async function prepareCheckout({ alt, details, wanted }) {
    const route = await checkoutUrlFor(alt.url, wanted).catch((e) => {
      ST.log.error("prepare: couldn't inspect the store, using the product page", e.message);
      return { url: alt.url, method: "product-page" };
    });
    ST.log("prepare: route chosen", { merchant: alt.merchant, method: route.method, url: route.url });
    const record = ST.handoff.record(route.url, alt.merchant, details, route.method !== "product-page", wanted, alt.url);
    // The hand-off follows this tab, so it keeps going if the link leads to another site (a search or listing
    // page, a redirect to the store). The record is saved long before the new page's scripts run.
    const tab = await chrome.tabs.create({ url: route.url });
    record.tabId = tab.id;
    await chrome.storage.local.set({ [ST.handoff.KEY]: record });
    return route;
  }

  ST.prepare = { checkoutUrlFor, prepareCheckout, pickVariant };
})();

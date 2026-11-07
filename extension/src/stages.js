// The buying journey, so the extension speaks up at the right moment:
//   product page   -> nothing visible; adding to basket starts a silent price check
//   basket page    -> a small "cheaper elsewhere" pill, if there is one
//   checkout page  -> glow + budget verdict (instant, reusing the silent check)
//   "Place order"  -> one pause, only when it would go over budget
globalThis.ST = globalThis.ST || {};

(() => {
  // Anything that puts the item in a cart, basket, bag or trolley: "Add to bag", "Add to shopping bag", "Add item to
  // your cart", "Move to basket", a plain "Add" / "+ Add" / "Add £5", and pre-orders (any dash or space).
  // Not links that only go there ("Go to bag", "Back to cart").
  const ADD_TO_BASKET = /\bto (\S+ ){0,2}(cart|basket|bag|trolley)\b|^\W*add\W*$|^\W*add\W*[£$€\d]|\bpre[\s\u2010-\u2015-]?order|^\W*reserve\b/i;
  const JUST_GOING = /^\W*(go|back|return|continue|proceed|view|see|open|show|edit)\b|\b(view|go to|back to|return to) (your |my )?(shopping )?(cart|basket|bag|trolley)/i;
  const isAddLabel = (t) => ADD_TO_BASKET.test(t) && !JUST_GOING.test(t);
  // How the button is coded (id/class/name/data-*), for icon-only buttons or labels in a language we don't match.
  const ADD_TO_BASKET_CODE = /add[-_]?(to[-_]?)?(cart|basket|bag|trolley)|pre[-_]?order/i;
  // The final buy button, by label or by how it's coded (id/class/data-*).
  const PLACE_ORDER_LABEL = /place (your )?order|complete (your )?(order|purchase)|confirm (and|&) pay|confirm (order|purchase|payment)|submit order|pay now|^pay\b|\bpay (£|\$|€|securely)|buy now/i;
  const PLACE_ORDER_CODE = /(place|submit|complete|confirm)[-_ ]?(your[-_ ]?)?(order|purchase|payment)|pay[-_ ]?(now|button|btn|submit)|submit[-_ ]?payment/i;

  const labelOf = (el) => (el.getAttribute("aria-label") || el.textContent || el.value || "").replace(/\s+/g, " ").trim();
  const clickable = (t) => t?.closest?.('button, a, input[type="submit"], input[type="button"], [role="button"]');
  const codeOf = (el) =>
    [el.id, el.getAttribute("name"), el.getAttribute("class"), ...[...el.attributes].filter((a) => a.name.startsWith("data-")).map((a) => a.value)]
      .filter(Boolean)
      .join(" ");

  function isBasketPage() {
    if (ST.detect.isCheckout()) return false;
    return /\/(cart|basket|bag|trolley)(\/|$|\?|\.|-)/i.test(location.pathname) ||
      /\b(basket|trolley|shopping bag|your bag|your cart|shopping cart)\b/i.test(document.title);
  }

  const isPlaceOrder = (el) => !!el && (PLACE_ORDER_LABEL.test(labelOf(el)) || PLACE_ORDER_CODE.test(codeOf(el)));

  // Name, price and currency of the product on this page: structured data first, then meta tags, then the page.
  function productInfo() {
    const meta = (n) => document.querySelector(`meta[property="${n}"], meta[name="${n}"]`)?.content;
    let name = "";
    let price = null;
    let currency = null;
    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const nodes = [JSON.parse(s.textContent)].flat().flatMap((d) => d["@graph"] || [d]);
        const p = nodes.find((d) => /product/i.test([].concat(d["@type"]).join(" ")));
        if (!p) continue;
        name = p.name || name;
        const offer = [].concat(p.offers || [])[0];
        const amount = offer?.price ?? offer?.lowPrice;
        if (amount != null) {
          price = Number(amount);
          currency = offer.priceCurrency || null;
        }
        break;
      } catch {}
    }
    if (price == null) {
      const el = document.querySelector('[itemprop="price"]');
      const raw = meta("product:price:amount") || meta("og:price:amount") || el?.getAttribute("content") || el?.textContent;
      if (raw) price = Number(String(raw).replace(/[^0-9.]/g, ""));
      currency = meta("product:price:currency") || meta("og:price:currency") || null;
    }
    const h1 = document.querySelector("h1");
    if (price == null || !Number.isFinite(price)) {
      const near = ST.detect.parseMoney((h1?.closest("main, section, article, form, div")?.innerText || "").slice(0, 2000));
      price = near?.amount ?? null;
      currency = currency || near?.currency || null;
    }
    name = (name || h1?.textContent || meta("og:title") || document.title).replace(/\s+/g, " ").trim().slice(0, 150);
    return { name, price: Number.isFinite(price) ? price : null, currency };
  }

  // A price-check request for the product on this page (same shape as a checkout analysis).
  function productPayload() {
    const base = ST.detect.scrape();
    const p = productInfo();
    return {
      ...base,
      stage: "add-to-basket",
      total: p.price,
      currency: p.currency || base.currency,
      items: [{ name: p.name, variant: "", qty: 1, price: p.price }],
    };
  }

  // Calls `cb(button)` when the shopper clicks an add-to-basket / pre-order button.
  function onAddToBasket(cb) {
    window.addEventListener(
      "click",
      (e) => {
        const el = clickable(e.target);
        if (!el) return;
        const label = labelOf(el);
        // By label (aria-label, text or value), or by how it's coded when the label is just an icon.
        const byLabel = [el.getAttribute("aria-label"), el.textContent, el.value].some((t) => t && isAddLabel(t.replace(/\s+/g, " ").trim().slice(0, 60)));
        if (byLabel || (!PLACE_ORDER_LABEL.test(label) && ADD_TO_BASKET_CODE.test(codeOf(el)))) cb(el, label);
      },
      true
    );
  }

  ST.stages = { isBasketPage, isPlaceOrder, productInfo, productPayload, onAddToBasket, clickable, labelOf };
})();

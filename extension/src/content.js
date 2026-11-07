// Entry point: watches for checkout pages, runs the analysis and wires the overlay to the backend.
(() => {
  const ST = globalThis.ST;
  const html = document.documentElement;
  if (html.dataset.secondThought) return; // already running (e.g. demo page + extension)
  html.dataset.secondThought = "1";

  const VERDICTS = ["good", "caution", "reconsider", "neutral"];
  const VARIANTS = ["primary", "secondary", "ghost"];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  // Closing the panel keeps the extension quiet on this store for the rest of the session.
  const dismissedKey = () => `second-thought:quiet:${location.hostname}`;
  const isQuiet = () => {
    try { return !!sessionStorage.getItem(dismissedKey()); } catch { return false; }
  };

  const overlay = new ST.Overlay();
  overlay.onClose = () => {
    try { sessionStorage.setItem(dismissedKey(), "1"); } catch {}
  };

  let running = false;
  let handledHref = null;
  let lastPayload = null;
  let lastResult = null;

  const money = (n, currency, digits = 2) => {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency, minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
    } catch {
      return n.toFixed(digits);
    }
  };
  const isWebUrl = (u) => {
    try { return ["http:", "https:"].includes(new URL(u).protocol); } catch { return false; }
  };

  // Cheaper options, cheapest first. Savings are worked out from the scraped total if the backend doesn't send them.
  function normalizeAlternatives(list, payload) {
    return (Array.isArray(list) ? list : [])
      .filter((a) => a && a.merchant && isWebUrl(a.url) && Number.isFinite(Number(a.price)))
      .filter((a) => !ST.excludedStore(a)) // left out for now, whoever suggested it (AI, mock or backend)
      .map((a) => {
        const price = Number(a.price);
        const currency = a.currency || payload?.currency || "GBP";
        const savings = a.savings != null ? Number(a.savings) : payload?.total != null ? payload.total - price : null;
        return {
          merchant: String(a.merchant),
          url: String(a.url),
          note: a.note ? String(a.note) : "",
          variant: a.variant ? String(a.variant) : "",
          // Backends that don't say are assumed to send exact matches.
          match: ["exact", "different_variant", "similar_item"].includes(a.match) ? a.match : "exact",
          matchNote: a.matchNote ? String(a.matchNote) : "",
          price,
          priceText: money(price, currency),
          savings,
          savingsText: savings > 0 ? `Save ${money(savings, currency)}` : "",
          savingsShort: savings > 0 ? money(savings, currency, savings >= 100 ? 0 : 2) : "",
        };
      })
      .filter((a) => a.savings == null || a.savings > 0) // only show it if it's actually cheaper
      .sort((a, b) => (a.match !== "exact") - (b.match !== "exact") || a.price - b.price) // exact matches first
      .slice(0, 3);
  }

  // Model text can arrive with markdown citations and tracking links: keep just the words.
  const plain = (t) =>
    String(t || "")
      .replace(/\(?\[([^\]]*)\]\([^)]*\)\)?/g, "")
      .replace(/https?:\/\/\S+/g, "")
      .replace(/\s+([.,;])/g, "$1")
      .replace(/\s{2,}/g, " ")
      .trim();

  // "Likely cheaper soon": only shown when there's a drop worth waiting for (likely/possible, and below the total).
  function normalizeOutlook(o, payload) {
    if (!o || !["likely", "possible"].includes(o.likelihood) || !o.reason) return null;
    const currency = payload?.currency || "GBP";
    const expected = Number(o.expectedPrice) > 0 ? Number(o.expectedPrice) : null;
    if (expected != null && payload?.total != null && expected >= payload.total) return null;
    const date = /^\d{4}-\d{2}-\d{2}$/.test(o.byDate || "") ? new Date(`${o.byDate}T12:00:00`) : null;
    return {
      likelihood: o.likelihood,
      expectedPrice: expected,
      expectedText: expected != null ? money(expected, currency) : "",
      byDate: date ? o.byDate : "",
      byText: date ? date.toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "",
      reason: plain(o.reason),
      signals: (Array.isArray(o.signals) ? o.signals : []).slice(0, 3).map(plain).filter(Boolean),
    };
  }

  // Be forgiving about what the backend sends so a bad response never breaks the page.
  function normalize(r, payload) {
    const str = (v) => (v == null ? "" : String(v));
    const actions = (Array.isArray(r?.actions) ? r.actions : [])
      .filter((a) => a && a.id && a.label)
      .slice(0, 4)
      .map((a) => ({
        id: str(a.id),
        label: str(a.label),
        variant: VARIANTS.includes(a.variant) ? a.variant : "secondary",
        confirmation: a.confirmation ? str(a.confirmation) : null,
      }));
    return {
      verdict: VERDICTS.includes(r?.verdict) ? r.verdict : "neutral",
      title: str(r?.title) || "Here's what we found",
      message: str(r?.message),
      insights: (Array.isArray(r?.insights) ? r.insights : [])
        .filter((i) => i && i.label != null && i.value != null)
        .slice(0, 4)
        .map((i) => ({ label: str(i.label), value: str(i.value) })),
      actions: actions.length ? actions : [{ id: "proceed", label: "Continue", variant: "primary" }],
      alternatives: normalizeAlternatives(r?.alternatives, payload),
      priceOutlook: normalizeOutlook(r?.priceOutlook, payload),
      fromEarlierCheck: !!r?.fromEarlierCheck,
      budgetInfo: r?.budgetInfo && Number.isFinite(Number(r.budgetInfo.left)) ? { ...r.budgetInfo, left: Number(r.budgetInfo.left) } : null,
      chart: r?.chart && Number.isFinite(r.chart.start) && Number.isFinite(r.chart.goal) ? r.chart : null,
      sessionId: r?.sessionId ?? null,
    };
  }

  async function handleAction(action) {
    if (action.id === "retry") return run({ force: true });
    if (action.id === "alternative") return switchStore(action);
    // Stop the cheaper-price search (its answer is ignored; it may still finish and be reused at checkout).
    if (action.id === "stop_search") {
      if (search) search.stopped = true;
      ST.log("price search: stopped by the shopper");
      lastResult = { ...lastResult, searching: false };
      return overlay.showResult(lastResult, handleAction, overlay.stepIndex);
    }
    // Said "I still want to buy it" / "Buy here anyway" past the over-budget decision: no second pause at Place order.
    if ((action.id === "buy_now" || action.id === "proceed") && lastResult?.verdict === "reconsider") pausedOnce = true;
    // On to the next decision; the panel moves itself.
    if (action.id === "buy_now") return reportAction(action);

    reportAction(action);
    if (action.confirmation) overlay.showConfirmation(action.confirmation);
    else overlay.dismiss(true);
  }

  // Tell the backend what the user chose; don't block the UI on it.
  function reportAction(action) {
    ST.api
      .action({
        actionId: action.id,
        sessionId: lastResult?.sessionId,
        verdict: lastResult?.verdict,
        alternative: action.alternative ? { merchant: action.alternative.merchant, url: action.alternative.url, price: action.alternative.price } : undefined,
        outlook: action.id === "watch" ? lastResult?.priceOutlook : undefined,
        purchase: lastPayload,
      })
      .catch(() => {});
  }

  // "Go to checkout at X": show a preparing state while the background finds the fastest route to X's checkout
  // (basket link where the store supports one), then open it. X's page fills in the details (handoff.js).
  async function switchStore(action) {
    const alt = action.alternative;
    // Not the exact item (other colour/size, or a similar product): say so and let the shopper decide first.
    if (alt.match !== "exact" && !action.confirmed) {
      return overlay.showMismatch(alt, {
        onContinue: () => switchStore({ ...action, confirmed: true }),
        onBack: () => overlay.showResult(lastResult, handleAction, overlay.stepIndex),
      });
    }
    reportAction(action);
    ST.log("switch: clicked alternative", { merchant: alt.merchant, url: alt.url, match: alt.match, price: alt.price });
    overlay.showAnalysing(
      [`Checking how ${alt.merchant}'s checkout works`, "Adding your items to the basket", "Opening checkout"],
      `Preparing your checkout at ${alt.merchant}`
    );
    const started = Date.now();
    let route = null;
    try {
      // Re-read the page now: the shopper may have changed payment method or options since the analysis.
      const now = ST.detect.scrape();
      const item = now.items[0] || lastPayload?.items?.[0] || {};
      const wanted = {
        name: item.name || lastPayload?.pageTitle || "",
        // Exact match: the shopper's own variant. Otherwise the variant they just agreed to.
        variant: alt.match === "exact" ? item.variant || "" : alt.variant || "",
        qty: item.qty || 1,
        // What they picked on this checkout; else their saved preference from the account page.
        paymentMethod: now.paymentMethod || lastPayload?.paymentMethod || (await ST.handoff.savedPaymentMethod()),
      };
      const details = await ST.handoff.collectDetails();
      ST.log("switch: wanted item", { ...wanted, detailFields: Object.keys(details) });
      route = await ST.api.prepareCheckout({ alt, details, wanted });
      ST.log("switch: route", route);
    } catch (e) {
      ST.log.error("switch: preparing failed, opening the link as-is", e.message);
    }
    await sleep(2200 - (Date.now() - started));
    await overlay.finishSteps();

    if (!route) {
      window.open(alt.url, "_blank", "noopener");
      return overlay.showConfirmation(`Opened ${alt.merchant}. Add the item to your basket there.`, 2600);
    }
    if (route.sameTab) return location.assign(route.url);
    overlay.showConfirmation(
      route.method === "product-page"
        ? `Opened ${alt.merchant}. We'll add it to your basket and fill in your details.`
        : `Opened ${alt.merchant} with your basket ready. We'll fill in your details.`,
      2600
    );
  }

  // No budget saved: don't pretend to check one. (Demo page, no extension storage: show them all, the mock has a budget.)
  async function analysisSteps() {
    const steps = ST.config.ANALYSIS_STEPS;
    if (typeof chrome === "undefined" || !chrome.storage?.local) return steps;
    try {
      const { budget } = await chrome.storage.local.get("budget");
      return budget > 0 ? steps : steps.filter((s) => !/budget/i.test(s));
    } catch {
      return steps;
    }
  }

  async function run({ force = false } = {}) {
    if (running) return;
    if (!force && isQuiet()) return;
    running = true;
    handledHref = location.href;

    overlay.showAnalysing(await analysisSteps());
    const payload = ST.detect.scrape();
    ST.log("analyse: start", {
      url: location.href,
      total: payload.total,
      currency: payload.currency,
      items: payload.items,
      paymentMethod: payload.paymentMethod,
    });
    const error = await analyse(payload, ST.api.analyze, "analyse");
    if (error) await overlay.showError(`Something went wrong: ${error.message}`, handleAction);
    running = false;
  }

  // Run the full check (price search + affordability + "could it get cheaper?") and show it. The cheaper-price search
  // can take a minute, but the affordability model answers in a moment and the outlook usually sooner than the search,
  // so a "can't afford" or "could get cheaper" decision shows as soon as it's known, with "Still searching for a better
  // price" underneath (Stop ends it). Returns the error if the full check failed with nothing shown.
  let search = null;
  async function analyse(payload, fullCheck, where) {
    const started = Date.now();
    lastPayload = payload;
    const full = fullCheck(payload).then((r) => normalize(r, payload));
    full.catch(() => {});
    const FULL = {};
    const fullDone = full.then(() => FULL, () => FULL);

    // Answered at once (e.g. reused from Add to basket): no partial answers needed, and no extra searches started.
    let afford = null;
    let outlookNow = null;
    let outlook = null;
    if ((await Promise.race([fullDone, sleep(400)])) !== FULL) {
      // The outlook request shares its search with the full check (same request, cached in the background).
      outlook = ST.api.outlook(payload).then((o) => normalizeOutlook(o, payload), () => null);
      const a = await Promise.race([fullDone, ST.api.afford(payload).catch(() => null)]);
      if (a !== FULL && a?.verdict === "reconsider") afford = a;
      else {
        const o = await Promise.race([fullDone, outlook]);
        if (o !== FULL && o) outlookNow = o;
      }
    }

    // "Could get cheaper" is its own search and often finishes after the price search: add it to whatever is showing
    // (the panel, or the quiet note, which becomes a panel), without moving the shopper off their step.
    const mine = (search = { stopped: false });
    let shown = null;
    let quiet = false;
    const addOutlook = async (o) => {
      if (!o || mine.stopped || !shown || lastResult !== shown || shown.priceOutlook) return;
      shown.priceOutlook = o;
      ST.log(`${where}: could get cheaper (${o.likelihood}), added to the panel`);
      if (overlay.current) overlay.updateResult(shown);
      else if (quiet && !isQuiet()) quiet = await present(shown, where);
    };

    if (afford || outlookNow) {
      ST.log(`${where}: showing "${afford ? "can't afford" : "could get cheaper"}" while the price search runs`);
      await sleep(1500 - (Date.now() - started));
      const partial = { ...normalize(afford || {}, payload), priceOutlook: outlookNow, searching: true };
      if (!afford) partial.verdict = "neutral"; // affordability comes with the full answer
      const current = () => !mine.stopped && lastResult === partial;
      shown = lastResult = partial;
      await overlay.showResult(partial, handleAction);
      outlook?.then(addOutlook);
      full.then(
        (result) => {
          logResult(where, result, started);
          if (!current()) return;
          result.priceOutlook ||= partial.priceOutlook;
          shown = lastResult = result;
          overlay.updateResult(result);
        },
        (e) => {
          ST.log.error(`${where}: price search failed`, e.message);
          if (!current()) return;
          partial.searching = false;
          overlay.updateResult(partial);
        }
      );
      return null;
    }

    let result;
    try {
      result = await full;
      logResult(where, result, started);
    } catch (e) {
      ST.log.error(`${where}: failed`, e.message);
      return e;
    }
    // Answer already known from the basket: a short glow, not the full "analysing" wait.
    await sleep((result.fromEarlierCheck ? 1200 : ST.config.MIN_ANALYSING_MS) - (Date.now() - started));
    shown = lastResult = result;
    quiet = await present(result, where);
    if (!result.priceOutlook) outlook?.then(addOutlook);
    return null;
  }

  function logResult(where, result, started) {
    ST.log(`${where}: result`, {
      seconds: ((Date.now() - started) / 1000).toFixed(1),
      verdict: result.verdict,
      couldGetCheaper: result.priceOutlook?.likelihood ?? null,
      alternatives: result.alternatives.map((a) => `${a.merchant} ${a.priceText} (${a.match}) ${a.url}`),
    });
  }

  // One decision, or a small note that fades when there's nothing to decide (affordable, nothing cheaper, no drop).
  // Returns true when it was the note.
  async function present(result, where) {
    if (overlay.decisions(result).length) {
      await overlay.showResult(result, handleAction);
      return false;
    }
    ST.log(`${where}: nothing to decide, showing a quiet note`, { verdict: result.verdict });
    overlay.showQuiet({
      title: { good: "Fits your budget", caution: "Worth a pause" }[result.verdict] || "No cheaper price found",
      sub: result.verdict === "good" || result.verdict === "caution" ? result.message : "We didn't find it cheaper at other stores.",
      tone: result.verdict === "caution" ? "caution" : result.verdict === "good" ? "good" : "neutral",
    });
    return true;
  }

  // ---------- Earlier stages (stages.js) ----------

  // Product page: adding to basket checks it there and then (glow, then one decision), and the checkout reuses it.
  ST.stages.onAddToBasket(async (el, label) => {
    if (ST.detect.isCheckoutUrl()) return ST.log("add to basket: clicked, but this is a checkout page, so skipped", { button: label });
    const payload = ST.stages.productPayload();
    const item = payload.items[0];
    if (!item.name || payload.total == null) {
      ST.log("add to basket: couldn't read the product, skipped the early check", { name: item.name, price: payload.total });
      return;
    }
    // Closed on this store already, or a check is showing: just remember the price check for the checkout.
    if (isQuiet() || running) {
      ST.log("add to basket: checking prices quietly", { item: item.name, price: payload.total });
      return ST.api.precheck(payload).catch((e) => ST.log.error("precheck failed", e.message));
    }
    running = true;
    handledHref = location.href;
    ST.log("add to basket: checking now", { item: item.name, price: payload.total });
    overlay.showAnalysing(await analysisSteps());
    // No error panel here: the item is in the basket and the checkout will try again.
    if (await analyse(payload, ST.api.precheck, "add to basket")) overlay.dismiss(false);
    running = false;
  });

  // Basket page: the moment to mention a cheaper price, before any forms. A small pill, no glow.
  async function basketStage() {
    handledHref = location.href;
    if (isQuiet()) return;
    const payload = { ...ST.detect.scrape(), stage: "basket" };
    if (!payload.items.length || payload.total == null) return;
    ST.log("basket: checking prices quietly", { items: payload.items.map((i) => i.name), total: payload.total });
    let result;
    try {
      result = normalize(await ST.api.precheck(payload), payload);
    } catch (e) {
      ST.log.error("basket: price check failed", e.message);
      return;
    }
    if (handledHref !== location.href || isQuiet()) return;
    lastPayload = payload;
    lastResult = result;
    const best = result.alternatives[0];
    if (!best) return ST.log("basket: nothing cheaper, staying quiet");
    ST.log("basket: showing the cheaper-elsewhere pill", { merchant: best.merchant, price: best.price });
    overlay.showNudge({
      title: `${best.savingsShort ? `${best.savingsShort} cheaper` : "Cheaper"} at ${best.merchant}`,
      sub: best.match === "exact" ? `Same item, ${best.priceText}` : best.matchNote || "A different version",
      cta: "See",
      onOpen: () => overlay.showResult(result, handleAction),
    });
  }

  // "Place order" while over budget: pause once with the numbers. Never blocks: "Buy anyway" lets the next click
  // through. Shown even if the panel was dismissed earlier, because this is the moment that matters.
  let pausedOnce = false;
  function placeOrderGuard(e) {
    if (pausedOnce || !lastResult?.budgetInfo || lastPayload?.total == null || !ST.detect.isCheckout()) return;
    const el = e.type === "submit" ? e.submitter || e.target.querySelector?.('[type="submit"]') : ST.stages.clickable(e.target);
    if (!ST.stages.isPlaceOrder(el)) return;
    const { left, safe, payday } = lastResult.budgetInfo;
    const total = lastPayload.total;
    // The tighter of the two limits: the shopping budget, or (with a bank picture) what's safe before payday.
    const bankBound = safe != null && safe < left;
    const limit = bankBound ? safe : left;
    if (total <= limit) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    pausedOnce = true;
    const cur = lastPayload.currency;
    const alt = lastResult.alternatives?.[0];
    ST.log("place order: paused once, over budget", { total, left, safe, button: ST.stages.labelOf(el) });
    overlay.showOverBudget({
      overBy: money(total - limit, cur),
      left: money(Math.max(limit, 0), cur),
      total: money(total, cur),
      leftLabel: lastResult.budgetInfo.leftLabel || (bankBound ? `safe to spend before payday${payday ? ` (in ${payday.inDays} days)` : ""}` : "left this month"),
      alt,
      onStop: () => {
        reportAction({ id: "not_now" });
        overlay.showConfirmation("Good call. Your basket is still here if you change your mind.", 2600);
      },
      onBuyAnyway: () => {
        reportAction({ id: "buy_anyway" });
        overlay.showConfirmation("OK. Click Place order again to finish.", 2600);
      },
      onSwitch: () => switchStore({ id: "alternative", alternative: alt }),
    });
  }
  window.addEventListener("click", placeOrderGuard, true);
  window.addEventListener("submit", placeOrderGuard, true);

  // Checkout pages are often SPAs or render late, so keep checking.
  // A hand-off to a cheaper store (see handoff.js) takes priority over analysing the page.
  let checking = false;
  async function check() {
    if (checking || running || handledHref === location.href) return;
    checking = true;
    try {
      if (await ST.handoff.resume(overlay)) handledHref = location.href;
      else if (ST.detect.isCheckout()) run();
      else if (ST.stages.isBasketPage()) basketStage();
    } catch (e) {
      // never let a hand-off problem break the page
      ST.log.error("page check failed", `${e.message}\n${e.stack || ""}`.slice(0, 600));
    } finally {
      checking = false;
    }
  }
  check();
  setInterval(check, 1000);

  // Toolbar icon click → force a run on this page.
  if (typeof chrome !== "undefined" && chrome.runtime?.onMessage) {
    chrome.runtime.onMessage.addListener((msg) => {
      if (msg?.type === "ST_RUN") {
        ST.log("toolbar: forced analysis", location.href);
        run({ force: true });
      }
    });
  }

  ST.run = run;
})();

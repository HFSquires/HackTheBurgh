// Real analysis without a backend: asks OpenAI (with web search) to check the basket and find the same items
// cheaper elsewhere. Runs in the background worker. Returns the same shape as the backend's /analyze.
globalThis.ST = globalThis.ST || {};

(() => {
  // Fast and cheap; supports web_search + structured outputs + low reasoning effort.
  // For harder product matching, gpt-6.1-sol is the step up. (gpt-5 itself retires 11 Dec 2026.)
  const DEFAULT_MODEL = "gpt-6-luna";
  const RETIRED = ["gpt-5", "gpt-5-mini", "gpt-5-nano"];
  // Tried in order when the account can't use the chosen model (new projects often lack the newest ones).
  const FALLBACKS = ["gpt-6-luna", "gpt-6.1-sol", "gpt-6", "gpt-5.5-mini", "gpt-5.5", "gpt-5.4-mini", "gpt-5.4", "gpt-5.2", "gpt-5.1", "gpt-4.1-mini", "gpt-4.1", "gpt-4o"];

  const noModelAccess = (status, msg) => (status === 403 || status === 404) && /model/i.test(msg || "");

  // First fallback this key can actually use, from /models. Remembered so later calls go straight to it.
  async function pickAvailableModel(settings, tried) {
    const api = ST.apiFor(settings.apiKey);
    const res = await fetch(`${api.base}/models`, { headers: { authorization: `Bearer ${settings.apiKey}` } }).catch(() => null);
    const ids = new Set(((await res?.json().catch(() => null))?.data || []).map((m) => m.id));
    const model = FALLBACKS.find((m) => ids.has(m) && !tried.includes(m));
    if (model) await chrome.storage.local.set({ model });
    return model || null;
  }

  const SCHEMA = {
    type: "object",
    additionalProperties: false,
    required: ["verdict", "title", "message", "insights", "checked", "alternatives"],
    properties: {
      verdict: {
        type: "string",
        enum: ["good", "caution", "reconsider", "neutral"],
        description: "Budget fit only. Never based on whether it's cheaper elsewhere",
      },
      title: { type: "string", description: "Short headline, max ~6 words" },
      message: { type: "string", description: "One or two plain sentences" },
      insights: {
        type: "array",
        description: "0-4 short facts, values formatted for display, e.g. '£222.49'",
        items: {
          type: "object",
          additionalProperties: false,
          required: ["label", "value"],
          properties: { label: { type: "string" }, value: { type: "string" } },
        },
      },
      checked: {
        type: "array",
        description: "Every price you actually saw for this item in search results, cheaper or not",
        items: {
          type: "object",
          additionalProperties: false,
          required: ["merchant", "price", "url"],
          properties: { merchant: { type: "string" }, price: { type: "number" }, url: { type: "string" } },
        },
      },
      alternatives: {
        type: "array",
        description: "0-3 cheaper places to buy the same items, cheapest first",
        items: {
          type: "object",
          additionalProperties: false,
          required: ["merchant", "price", "currency", "url", "note", "variant", "match", "match_note"],
          properties: {
            merchant: { type: "string" },
            variant: { type: "string", description: "The listing's size/colour/capacity etc., '' if it has none" },
            match: {
              type: "string",
              enum: ["exact", "different_variant", "similar_item"],
              description: "exact = same product and same variant the shopper chose",
            },
            match_note: { type: "string", description: "If not exact, what differs in a few words, e.g. 'Black, not Navy'. '' if exact" },
            price: { type: "number", description: "Total for the same basket incl. delivery" },
            currency: { type: "string", description: "ISO code, e.g. GBP" },
            url: { type: "string", description: "A URL you actually found in search results" },
            note: { type: "string", description: "Short, e.g. 'Same item · free delivery'" },
          },
        },
      },
    },
  };

  const SYSTEM = `You help people make a good money decision at the moment they check out online.
You get what's in their basket on a checkout page, plus (optionally) their monthly shopping budget.

Do two things:
1. First work out exactly what the shopper chose: product, and variant (size, colour, capacity, etc.) and quantity, from the items and page text. Then ALWAYS search the web (never answer from memory: prices change daily) for the SAME items (same brand, model, size/variant) for less at other reputable retailers that ship to the shopper's country (infer it from the currency and the store's domain). Only include an alternative if you found a real listing with a current price lower than the shopper's total, and use the exact URL from your search results. Use the product page URL. Include delivery in the price when you can tell. Search properly: look at several of the big retailers for that kind of product in that country and at least one price comparison site (for example in the UK: Argos, Currys, John Lewis, Tesco, Very, eBay new, plus specialists like GAME, ShopTo, CeX or Smyths for games; PriceSpy, PriceRunner or Google Shopping). Use more than one search query. List every price you saw in "checked". Any checked listing for the same item that is cheaper than the shopper's total (including delivery) MUST be in "alternatives". Pre-orders count: compare pre-order prices. Never invent stores, prices or URLs; an empty list is fine.${(ST.config.EXCLUDED_STORES || []).length ? ` Never suggest these stores, not even as a price you checked: ${ST.config.EXCLUDED_STORES.join(", ")}.` : ""} Prefer exact matches (same variant). Only include a different variant or a very similar product if it is clearly cheaper, and then set match and match_note honestly so the shopper is warned.
2. Give a verdict about the BUDGET ONLY. It must not depend on whether you found it cheaper elsewhere; that is shown to the shopper separately as "alternatives":
   - "good": fits comfortably in what's left of the monthly budget;
   - "caution": fits, but uses most of what's left (roughly over 60%);
   - "reconsider": costs more than what's left;
   - "neutral": no budget information was given.
   Title and message are about the budget (for "neutral", a short neutral summary). Never claim it's "the best price" or "the cheapest"; if you found nothing cheaper, say you didn't find it cheaper at the stores you checked. If you found a cheaper option you may mention it in one short clause of the message, but keep the verdict about the budget.

Keep the tone friendly and short. Format money for display in the shopper's currency.`;

  function buildPrompt(p, settings) {
    const budget =
      settings.budget > 0
        ? `Monthly shopping budget: ${settings.budget} ${p.currency}. Already spent this month: ${settings.spent || 0} ${p.currency}.`
        : "No budget information.";
    // Bank picture (persona.js, or a bank connection): lets the message say "with rent due in 6 days".
    const b = settings.money && ST.persona ? ST.persona.safeToSpend(settings.money) : null;
    const bank = b
      ? `Bank: current balance ${b.balance} ${b.currency}. Bills due before the next payday: ${b.upcoming.map((u) => `${u.name} ${u.amount} in ${u.inDays} days`).join(", ") || "none"} (total ${b.committed}). Safe to spend before payday: ${b.safe} ${b.currency}.${b.payday ? ` Next income: ${b.payday.name} ${b.payday.amount} in ${b.payday.inDays} days.` : ""}${settings.money.savings ? ` Savings: ${settings.money.savings.balance} towards ${settings.money.savings.goalName || "a goal"} (${settings.money.savings.goal}).` : ""} If the total is more than what's safe to spend, the verdict is "reconsider" even if it fits the shopping budget; mention the bill that makes it tight.`
      : "";
    return [
      `Today is ${new Date().toDateString()}.`,
      `Store: ${p.merchant} (${p.url})`,
      `Checkout total: ${p.total ?? "unknown"} ${p.currency}`,
      `Items found on the page: ${JSON.stringify(p.items)}`,
      budget,
      bank,
      `Checkout page text (may include the items if the list above is empty):\n${p.pageText}`,
    ].join("\n");
  }

  // One Responses API call with a strict JSON schema; returns the parsed JSON.
  // Returns { json, searches }: the parsed answer, and the web searches the model actually ran.
  async function respond(settings, { instructions, input, name, schema, tools, effort = "low", mustUseTools = false }) {
    let model = !settings.model || RETIRED.includes(settings.model) ? DEFAULT_MODEL : settings.model;
    const body = { model, instructions, input, text: { format: { type: "json_schema", name, strict: true, schema } } };
    if (tools) body.tools = tools;
    if (tools && mustUseTools) body.tool_choice = "required";
    // Reasoning models: effort trades speed for care (low for page steps, medium for the price search).
    const setModel = (m) => {
      model = body.model = m;
      if (/^(gpt-[5-9]|o\d)/.test(m)) body.reasoning = { effort };
      else delete body.reasoning;
    };
    setModel(model);

    const api = ST.apiFor(settings.apiKey);
    const send = () =>
      fetch(`${api.base}/responses`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${settings.apiKey}` },
        body: JSON.stringify(body),
      });
    let res = await send();
    let data = await res.json().catch(() => null);
    // Some models/proxies don't accept a forced tool call: retry letting the model choose.
    if (!res.ok && res.status === 400 && body.tool_choice && /tool_choice/i.test(data?.error?.message || "")) {
      ST.log.error(`${api.name}: forced web search not accepted, retrying ${name} without forcing it`, data?.error?.message);
      delete body.tool_choice;
      res = await send();
      data = await res.json().catch(() => null);
    }
    // A proxy (ELM) may not pass hosted tools through. Retry once without them rather than failing outright.
    if (!res.ok && res.status === 400 && body.tools && /tool|web_search/i.test(data?.error?.message || "")) {
      ST.log.error(`${api.name}: tools rejected, retrying ${name} without web search`, data?.error?.message);
      delete body.tools;
      delete body.tool_choice;
      res = await send();
      data = await res.json().catch(() => null);
    }
    // The account can't use this model: switch to one it can, and remember it.
    if (!res.ok && noModelAccess(res.status, data?.error?.message)) {
      const fallback = await pickAvailableModel(settings, [model]);
      ST.log.error(`${api.name}: no access to ${model}`, fallback ? `switching to ${fallback}` : "no fallback model available on this key");
      if (fallback) {
        setModel(fallback);
        settings.model = fallback;
        res = await send();
        data = await res.json().catch(() => null);
      }
    }
    if (!res.ok) {
      ST.log.error(`${api.name}: ${name} request failed`, { status: res.status, model, error: data?.error?.message });
      throw new Error(data?.error?.message || `${api.name} API ${res.status}`);
    }
    const searches = (data.output || [])
      .filter((o) => o.type === "web_search_call")
      .map((o) => o.action?.query || o.action?.queries?.join(" | ") || o.action?.url || o.action?.type || "(search)");
    ST.log(`${api.name}: ${name} answered`, {
      model,
      status: data.status,
      ...(body.tools ? { webSearches: searches.length, queries: searches } : {}),
      usage: data.usage && { input: data.usage.input_tokens, output: data.usage.output_tokens },
    });

    // The answer is the output_text inside the final "message" item (web search calls come before it).
    const text = (data.output || [])
      .filter((o) => o.type === "message")
      .flatMap((o) => o.content || [])
      .filter((c) => c.type === "output_text")
      .map((c) => c.text)
      .join("")
      .trim();
    if (!text) throw new Error(`No answer from ${api.name}`);
    return { json: JSON.parse(text), searches };
  }

  async function analyze(payload, settings) {
    const { json: result, searches } = await respond(settings, {
      instructions: SYSTEM,
      input: buildPrompt(payload, settings),
      name: "checkout_analysis",
      schema: SCHEMA,
      tools: [{ type: "web_search" }],
      mustUseTools: true,
      effort: "medium", // the price search is the core job; a few extra seconds beat a wrong "best price"
    });
    ST.log("analyse: prices the AI saw", result.checked?.length ? result.checked.map((c) => `${c.merchant} ${c.price} ${c.url}`) : "(none reported)");

    // Backend contract uses camelCase.
    result.alternatives = (result.alternatives || []).map(({ match_note, ...a }) => ({ ...a, matchNote: match_note }));
    const stores = new Set((result.checked || []).map((c) => c.merchant)).size;
    if (!searches.length) {
      // Without a search, "no cheaper option" means nothing. Say so instead of implying it's the best price.
      ST.log.error("analyse: no web search ran, so prices weren't compared", "The model or API proxy didn't search. Try a stronger model in settings, or a key with web search.");
      result.message = `${result.message} We couldn't compare prices this time, so it may be cheaper elsewhere.`.trim();
    } else if (!result.alternatives.length && stores) {
      result.insights = [...(result.insights || []), { label: "Prices compared", value: `${stores} store${stores === 1 ? "" : "s"}` }].slice(0, 4);
    }
    delete result.checked;
    return { ...result, actions: actionsFor(result) };
  }

  // ---------- Price outlook: likely to get cheaper if they wait? ----------
  // A separate call that runs alongside analyze(), so the price comparison isn't held up by the history research.

  const OUTLOOK_SCHEMA = {
    type: "object",
    additionalProperties: false,
    required: ["likelihood", "expected_price", "by_date", "reason", "signals"],
    properties: {
      likelihood: { type: "string", enum: ["likely", "possible", "unlikely", "unknown"] },
      expected_price: { type: "number", description: "Price you expect if they wait, in the shopper's currency. 0 if unknown" },
      by_date: { type: "string", description: "YYYY-MM-DD by which you expect it, '' if unknown" },
      reason: { type: "string", description: "At most 12 words, no links, e.g. 'Black Friday (27 Nov) may bring it to about £65.'" },
      signals: { type: "array", description: "0-3 evidence points you actually found, each under 10 words, no links", items: { type: "string" } },
    },
  };

  const OUTLOOK_SYSTEM = `A shopper is about to buy something online. Judge whether it's likely to be cheaper soon if they wait.
First work out exactly what they chose (product, variant, quantity) from the items and page text. Then search the web for evidence (never answer from memory): its price history (PriceSpy, PriceRunner, camelcamelcamel, Keepa or similar), how this kind of product usually moves (games and electronics often drop at launch, in the first weeks after, and in big sales), upcoming sales in the shopper's country within the next ~6 weeks (Black Friday, Cyber Monday, Boxing Day, Prime Day, store-specific sales), a newer model announced or due, or a pre-order price that retailers have been undercutting.
"likely" only with concrete evidence (it dropped in the same sale last year, a dated sale is close and this item is typically discounted, a successor launches soon); "possible" for a reasonable pattern without item-specific evidence; "unlikely" for essentials, already-discounted or price-stable items, or anything they need now; "unknown" if you couldn't tell. Give a realistic expected_price (in the shopper's currency, for the same basket) and by_date only when likely or possible. Never invent price history. The reason is one short line of at most 12 words; no links or citations anywhere.`;

  async function outlook(payload, settings) {
    const { json: o } = await respond(settings, {
      instructions: OUTLOOK_SYSTEM,
      input: buildPrompt(payload, {}),
      name: "price_outlook",
      schema: OUTLOOK_SCHEMA,
      tools: [{ type: "web_search" }],
      mustUseTools: true,
    });
    const result = {
      likelihood: o.likelihood || "unknown",
      expectedPrice: o.expected_price > 0 ? o.expected_price : null,
      byDate: o.by_date || "",
      reason: o.reason || "",
      signals: o.signals || [],
    };
    ST.log("outlook: answer", result);
    return result;
  }

  // ---------- AI fallback for getting to checkout on another store ----------

  const STEP_SCHEMA = {
    type: "object",
    additionalProperties: false,
    required: ["action", "index", "value", "reason", "question"],
    properties: {
      action: { type: "string", enum: ["click", "select", "done", "ask", "stuck"] },
      index: { type: "integer", description: "Element number from the list, -1 if none" },
      value: { type: "string", description: "For select: the option text to choose. Otherwise ''" },
      reason: { type: "string", description: "Shown to the shopper, under 8 words, e.g. 'Choosing size M'" },
      question: { type: "string", description: "For ask: one short question to the shopper, e.g. 'Which size do you want: 9, 10 or 11?'. Otherwise ''" },
    },
  };

  const STEP_SYSTEM = `You move a shopper one step at a time from a store's product or basket page to the checkout page, with the right item in the basket.
You get the item they want (name, variant such as size/colour, quantity), a numbered list of the page's buttons, links, options and dropdowns, and usually a screenshot of the page. Use the screenshot to understand the page (what's selected, what's out of stock, where the main product is) and answer with an element number from the list. Ignore the "Second Thought" panel in the screenshot; that's this assistant. Pick ONE next action:
- "click" the listing that matches the wanted item if this is a search results, category or comparison page (prefer a real store's product page);
- "select" (dropdown, give the option text) or "click" (option button/swatch) to choose the wanted variant, if the page needs it and it isn't already chosen;
- "click" the add to basket/bag/cart button once the variant is right;
- "click" the basket/bag/checkout button or link to move towards checkout;
- "done" if this is already the checkout page where delivery details are entered;
- "ask" if you need a detail only the shopper can give to carry on: which variant when the wanted one is unclear or missing (list the choices on the page), a postcode for a delivery check, a quantity, a choice between delivery options. Put one short question in "question". Their earlier answers are in "shopper_answers"; use them and don't ask the same thing twice;
- "stuck" if sign-in, a CAPTCHA, out of stock, or anything else blocks progress that the shopper can't fix by typing an answer (explain in reason).
Never ask for card details, bank details, passwords, codes sent by text or email, or to sign in.
Never pick anything that pays, places or confirms an order, uses an express wallet (Apple Pay, Google Pay, Shop Pay, PayPal), subscribes, signs in or creates an account, or that is unrelated to buying this item (cookie banners, newsletters, other products, navigation menus). A "Pre-order" / "Pre-Order Now" button on a product page just adds the item to the basket, so it's fine.
Elements may say where they lead: "goes_to" (a link's destination) and "submits_form_to" (where a button posts a form). Use these, not just the visible text, to judge what a click does. Never pick an element marked "blocked": it was found to place an order, pay, or need an account, whatever its label says.
"history" lists your earlier steps and what happened. If a step had "no visible change", do NOT repeat it: the control was probably already selected, or something else is needed next (a "Continue", "Checkout" or "Continue to checkout" button that is now available, a postcode, a delivery choice). Pick something different, ask, or say stuck.`;

  async function nextStep(payload, settings, image) {
    const content = [{ type: "input_text", text: JSON.stringify(payload) }];
    if (image) content.push({ type: "input_image", image_url: image, detail: "low" });
    const { json } = await respond(settings, {
      instructions: STEP_SYSTEM,
      input: [{ role: "user", content }],
      name: "next_step",
      schema: STEP_SCHEMA,
    });
    return json;
  }

  // Buttons are decided here, not by the model, so they always map to things the extension can do.
  // When a cheaper option exists, its green button is the main call to action, so "continue here" steps back.
  // A likely price drop gets its own "wait and notify me" button inside the outlook card (overlay.js), which arrives
  // later from its own call, so these stay about the budget.
  function actionsFor(r) {
    const cheaper = r.alternatives?.length > 0;
    if (r.verdict === "good" || r.verdict === "neutral") {
      return [
        { id: "proceed", label: cheaper ? "Buy here instead" : "Continue to pay", variant: cheaper ? "secondary" : "primary" },
        { id: "dismiss", label: "Dismiss", variant: "ghost" },
      ];
    }
    return [
      { id: "remind", label: "Remind me in 24h", variant: cheaper ? "secondary" : "primary", confirmation: "Got it. We'll remind you tomorrow." },
      { id: "proceed", label: "Buy here anyway", variant: "ghost" },
    ];
  }

  // ---------- Price watch: re-checks a waited-for item until it drops ----------

  const PRICE_SCHEMA = {
    type: "object",
    additionalProperties: false,
    required: ["found", "merchant", "price", "url"],
    properties: {
      found: { type: "boolean", description: "True only if you found a current, in-stock listing for the same item" },
      merchant: { type: "string" },
      price: { type: "number", description: "Lowest current price incl. delivery, 0 if not found" },
      url: { type: "string", description: "A URL you actually found in search results, '' if not found" },
    },
  };

  async function checkPrice(watch, settings) {
    const { json } = await respond(settings, {
      instructions: `Find the lowest current price for exactly this item (same product and variant), new, in stock, at a reputable retailer that ships to the shopper's country. Search the web; never answer from memory. Include delivery when you can tell. Never invent stores, prices or URLs.`,
      input: [
        `Today is ${new Date().toDateString()}.`,
        `Item: ${watch.item}${watch.variant ? ` (${watch.variant})` : ""}, quantity ${watch.qty || 1}`,
        `They nearly paid ${watch.paid} ${watch.currency} at ${watch.merchant} (${watch.url}).`,
      ].join("\n"),
      name: "price_check",
      schema: PRICE_SCHEMA,
      tools: [{ type: "web_search" }],
      mustUseTools: true,
    });
    return json;
  }

  // ---------- Wording the affordability model's answer ----------
  // The model decides; this only writes what the shopper reads, from the model's figures.

  const PHRASE_SCHEMA = {
    type: "object",
    additionalProperties: false,
    required: ["title", "message"],
    properties: {
      title: { type: "string", description: "At most 6 words: the situation" },
      message: { type: "string", description: "One sentence, at most 20 words" },
    },
  };
  const PHRASE_SYSTEM = `You write the words a checkout assistant shows a shopper. An affordability model has already decided; never change, soften or second-guess it, and use only the facts and numbers given (whole pounds; a minus sign for a balance below zero).
Plain British English, second person, direct, calm, no jargon ("net worth", "forecast", "projected"), no exclamation marks, no lecturing.
Title: at most 6 words, the consequence. Message: one sentence, at most 18 words, the number that matters most.
Order of what matters: can't pay at all (how much more it is than they have), then going overdrawn (how low the balance gets, and when), then the savings goal. For pay in 3, say whether spreading the payments avoids going overdrawn, comparing with paying now.
builtInWording is the safe default; keep its meaning, just say it more clearly.`;

  async function phraseDecision(facts, settings) {
    const { json } = await respond(settings, { instructions: PHRASE_SYSTEM, input: JSON.stringify(facts), name: "decision_words", schema: PHRASE_SCHEMA });
    if (!json?.title || !json?.message) throw new Error("no wording returned");
    return { title: String(json.title).slice(0, 60), message: String(json.message).slice(0, 200) };
  }

  // ---------- Form fields the rules couldn't place ----------
  // Gets labels and the kinds of saved details only, never the shopper's values.

  const FIELDS_SCHEMA = {
    type: "object",
    additionalProperties: false,
    required: ["matches"],
    properties: {
      matches: {
        type: "array",
        items: {
          type: "object",
          additionalProperties: false,
          required: ["field", "detail"],
          properties: { field: { type: "integer" }, detail: { type: "string" } },
        },
      },
    },
  };
  const FIELDS_SYSTEM = `You match empty checkout form fields to the kinds of details a shopper has saved. You get each field's label, name, placeholder, type and autocomplete, and the names of the saved details (never their values).
Match a field only when you're confident it asks for that detail, in any wording or language: "Pincode", "ZIP", "Eircode", "Postleitzahl" -> postcode; "Mobile" -> phone; "Town" -> city; "Re-type email" -> email; "House number and street" -> address1.
Never match anything about payment, cards, passwords, accounts, promo codes, gift messages or company names. Leave out anything you're unsure of.`;

  async function mapFields({ fields, details }, settings) {
    const { json } = await respond(settings, { instructions: FIELDS_SYSTEM, input: JSON.stringify({ fields, details }), name: "field_matches", schema: FIELDS_SCHEMA });
    const out = (json?.matches || []).filter((m) => details.includes(m.detail) && Number.isInteger(m.field));
    ST.log("ai: matched form fields", { asked: fields.length, matched: out.length });
    return out;
  }

  ST.live = { analyze, outlook, nextStep, checkPrice, phraseDecision, mapFields };
})();

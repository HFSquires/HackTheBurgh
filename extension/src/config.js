// Shared config. Loaded by content scripts, the background worker and the demo page.
globalThis.ST = globalThis.ST || {};

ST.config = {
  // Where the backend lives. Leave empty to use the built-in mock responses.
  // The background worker POSTs to `${BACKEND_URL}/analyze` and `${BACKEND_URL}/action`.
  BACKEND_URL: "",

  // Keep the "analysing" state on screen at least this long so it doesn't flash.
  MIN_ANALYSING_MS: 2600,

  // Steps shown while the backend is working. They advance on a timer (the analysis is one AI call), and the last one
  // stays on screen until the answer arrives, so it must name the slow part: the web search. Only list real work.
  // The budget step is left out when no budget is saved (content.js).
  // "Checking your accounts" is for the demo: no bank connection yet, it's shown but nothing is fetched.
  ANALYSIS_STEPS: [
    "Reading your basket",
    "Checking your accounts",
    "Checking this month's budget",
    "Searching other stores and price history",
  ],

  // Mock only: force a verdict ("good" | "caution" | "reconsider" | "error"), or null to pick by total.
  MOCK_SCENARIO: null,

  // Mock only: where the "cheaper elsewhere" link goes. Null = the demo checkout on localhost, no link elsewhere.
  MOCK_ALT_URL: null,

  // Your Second Thought account (web/ folder). Fill in after deploying it; empty = no sign-in button.
  // site: where the account page is hosted; auth0Domain / auth0ClientId: the same Auth0 app the page uses.
  ACCOUNT: {
    site: "", // e.g. "https://second-thought.vercel.app"
    auth0Domain: "", // e.g. "second-thought.eu.auth0.com"
    auth0ClientId: "",
  },

  // Demo page only: overrides the demo shopper's budget from persona.js (e.g. { budget: 400, spent: 240 }).
  // Null = use the persona's budget, balance and bills as they are.
  MOCK_BUDGET: null,
};

// OpenAI-compatible API to call for a given key. University of Edinburgh ELM keys ("elm-…") go through the
// ELM proxy, which serves the same OpenAI models and endpoints; anything else goes straight to OpenAI.
ST.apiFor = (key) =>
  /^elm-/i.test(key || "")
    ? { name: "ELM", base: "https://elm.edina.ac.uk/api/v1" }
    : { name: "OpenAI", base: "https://api.openai.com/v1" };

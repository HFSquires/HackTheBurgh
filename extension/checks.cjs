// Run: node extension/checks.cjs. Tests the actual adapter and decision-step selection without browser/network access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const load = (file, context) => vm.runInContext(fs.readFileSync(path.join(__dirname, 'src', file), 'utf8'), context);
(async () => {
  const calls = [];
  const d = { verdict: 'reconsider', risk: 'overdraft', title: 'Overdraft warning', message: 'Projected below zero.',
    today: '2026-11-02', month: '2026-11', price: 100, paymentPlan: 'pay_now',
    netWorth: { now: 1200, goal: 1350, forecastEndWithout: 1450 },
    cashFlow: { lowestWithPurchase: -50, forecastMonthEnd: 102.05, horizon: '2026-11-30' },
    savings: { monthlyTarget: 150, forecastSaved: 20, suggestedDailyBudget: 15 } };
  const context = vm.createContext({ Intl, AbortSignal, URL, Date, window: { matchMedia: () => ({ matches: false }) },
    fetch: async (url, options) => { calls.push(JSON.parse(options.body)); return { ok: true, json: async () => d }; } });
  load('config.js', context);
  context.ST.log = Object.assign(() => {}, { error() {} });
  load('precheck.js', context); load('overlay.js', context);
  const payload = { total: 100, currency: 'GBP', paymentOptions: [{ label: 'Klarna: pay in 3', paymentPlan: 'pay_in_3' }] };
  const settings = { bankPersona: 'persona001', monthlySavings: 150 };
  let result = await context.ST.precheck.modelVerdict(payload, settings);
  assert.equal(calls[0].monthlySavings, 150); assert.equal(calls[0].bank.persona, 'persona001');
  assert.equal(result.risk, 'overdraft'); assert.equal(result.financeAction.id, 'pay_in_3'); assert.equal(result.financeAction.label, 'Check Klarna: pay in 3');
  assert.equal(result.budgetInfo, null); assert.equal(result.chart.start, 1200);
  const prices = { alternatives: [{ merchant: 'A', price: 90 }], verdict: 'good' };
  result = await context.ST.precheck.withBudget(prices, { ...payload, total: 200 }, { ...settings, monthlySavings: 300 });
  assert.equal(calls.at(-1).price, 200); assert.equal(calls.at(-1).monthlySavings, 300);
  assert.equal(result.alternatives, prices.alternatives); assert.equal(result.risk, 'overdraft');
  d.paymentPlan = 'pay_in_3'; d.comparison = { payNow: { lowestWithPurchase: -150, forecastMonthEnd: 0 }, payIn3: d.cashFlow };
  d.payments = [{ amount: 33.33, date: '2026-11-02' }, { amount: 33.33, date: '2026-12-02' }, { amount: 33.34, date: '2027-01-02' }];
  result = await context.ST.precheck.modelVerdict({ ...payload, paymentPlan: 'pay_in_3' }, settings);
  assert.equal(calls.at(-1).paymentPlan, 'pay_in_3'); assert.equal(result.financeAction.id, 'pay_now');
  assert.match(result.comparison.schedule, /33.33/); assert.match(result.comparison.payNow, /150/);
  assert.equal(result.monthEnd.month, 'November 2026');
  assert.equal(result.monthEnd.payNow, 0);
  assert.equal(result.monthEnd.payIn3, 102.05);
  assert.equal(result.laterPayments, 'Upcoming payments: £33.33 in December and £33.34 in January.');
  for (const [risk, verdict] of [['overdraft', 'reconsider'], ['savings', 'caution'], ['none', 'good'], ['unknown', 'neutral']]) {
    const steps = context.ST.Overlay.prototype.decisions({ risk, verdict, alternatives: prices.alternatives, priceOutlook: {} });
    assert.deepEqual(Array.from(steps), ['budget', 'wait', 'switch']); // Retains the newer one-decision-at-a-time UI.
  }
  const countBefore = calls.length;
  assert.equal((await context.ST.precheck.modelVerdict({ ...payload, paymentPlan: 'pay_in_3', paymentOptions: [] }, settings)).risk, 'unknown');
  assert.equal((await context.ST.precheck.modelVerdict({ ...payload, paymentPlan: null }, settings)).risk, 'unknown');
  assert.equal(calls.length, countBefore); // Unsupported/unavailable checkout plans must never use an invented schedule.
  d.paymentPlan = 'pay_now'; d.comparison = null;
  assert.equal((await context.ST.precheck.modelVerdict({ ...payload, paymentOptions: [] }, settings)).financeAction, null);
  assert.equal(await context.ST.precheck.modelVerdict(payload, { bankPersona: '' }), null);
  assert.equal((await context.ST.precheck.modelVerdict({ ...payload, currency: 'USD' }, settings)).risk, 'unknown');
  context.fetch = async () => { throw new Error('offline'); };
  result = await context.ST.precheck.withBudget(prices, payload, settings);
  assert.equal(result.risk, 'unknown'); assert.equal(result.verdict, 'neutral'); assert.equal(result.chart, null);
  context.fetch = async () => ({ ok: true, json: async () => ({ title: 'No salary', verdict: 'neutral' }) });
  assert.equal((await context.ST.precheck.modelVerdict(payload, settings)).risk, 'unknown');
  const { cleanAccount, emptyAccount } = await import('../web/lib/validate.js');
  assert.equal(emptyAccount().budget.monthlySavings, 0);
  assert.equal(cleanAccount({ budget: { monthlySavings: 150 } }).account.budget.monthlySavings, 150);
  for (const goal of [-1, Infinity, NaN, true, '150', 1000001]) assert.ok(cleanAccount({ budget: { monthlySavings: goal } }).error);
  // Read actual payment controls, not provider logos or unrelated text.
  const radio = (text, checked = false, disabled = false, visible = true) => ({
    labels: [{ textContent: text, getClientRects: () => visible ? [{}] : [] }], checked, disabled,
    closest: () => null, getAttribute: () => null,
  });
  let controls = [radio('Credit or debit card', true), radio('PayPal'), radio('Klarna: pay in 3'), radio('Klarna pay in 30'), radio('Clearpay: pay in 4'), radio('Klarna pay in 3 weekly'), radio('Klarna pay in 3', false, true), radio('Klarna pay in 3', false, false, false)];
  context.document = { querySelectorAll: () => controls };
  load('detect.js', context);
  let options = context.ST.detect.paymentOptions();
  assert.equal(options.length, 6);
  assert.equal(options.filter(o => o.paymentPlan === 'pay_in_3').length, 1);
  assert.equal(options[0].selected, true);
  controls = [radio('PayPal pay in 3', true)];
  assert.equal(context.ST.detect.paymentOptions()[0].paymentPlan, 'pay_in_3');
  controls = [radio('Klarna pay in 3, 19% APR', true)];
  assert.equal(context.ST.detect.paymentOptions()[0].paymentPlan, null);
  let bankChecks = 0;
  context.ST.mock = {
    analyze: async () => {
      if (context.ST.config.MOCK_SCENARIO === 'error') throw new Error('Mock backend error');
      return { verdict: context.ST.config.MOCK_SCENARIO || 'caution', alternatives: [] };
    },
    outlook: async () => null,
  };
  context.ST.precheck.find = async () => null;
  context.ST.precheck.addOutlook = async () => {};
  context.ST.precheck.withBudget = async () => { bankChecks++; return { verdict: 'reconsider', risk: 'overdraft' }; };
  load('api.js', context);
  context.ST.config.MOCK_VERDICT_OVERRIDE = true;
  for (const selected of ['good', 'caution', 'reconsider', 'neutral', null]) {
    context.ST.config.MOCK_SCENARIO = selected;
    const answer = await context.ST.api.analyze(payload);
    assert.equal(answer.verdict, selected || 'caution');
    assert.equal(answer.mockVerdict, true);
    assert.equal(context.ST.Overlay.prototype.decisions(answer)[0], 'budget');
  }
  assert.equal(bankChecks, 0);
  assert.equal(await context.ST.api.afford(payload), null);
  assert.equal(await context.ST.api.outlook(payload), null);
  context.ST.config.MOCK_SCENARIO = 'error';
  await assert.rejects(context.ST.api.analyze(payload), /Mock backend error/);
  context.ST.config.MOCK_VERDICT_OVERRIDE = false;
  context.ST.config.MOCK_SCENARIO = null;
  assert.equal((await context.ST.api.analyze(payload)).risk, 'overdraft');
  assert.equal(bankChecks, 1);
  console.log('Frontend and mock-override checks passed, including all verdicts, errors and switching back to the bank model.');
})().catch(e => { console.error(e); process.exitCode = 1; });

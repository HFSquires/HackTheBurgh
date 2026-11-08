"""Focused overdraft/savings regression checks. Run: python model_checks.py. Writes no outputs."""
import copy
import datetime as dt
import json
from unittest.mock import patch
import model


def picture(balance=1500, savings=0, today=dt.date(2026, 4, 1)):
    tx, details = [], []
    for month, spend in [(1, 280), (2, 300), (3, 320)]:
        for day, desc, debit, credit, kind, mcc in [
            (5, 'SHOP', spend / 2, 0, 'DEB', 5411),
            (20, 'SHOP', spend / 2, 0, 'DEB', 5411),
            (10, 'RENT', 400, 0, 'DD', None),
            (25, 'SALARY', 0, 1000, 'BGC', None),
        ]:
            tx.append(dict(date=dt.date(2026, month, day), desc=desc, debit=debit, credit=credit, type=kind))
            details.append(dict(mcc=mcc, merchant=desc))
    main = dict(accountId='main', type='current', nickname='Everyday account', transactions=tx,
                transactionDetails=details, pending=[], standingOrders=[], directDebits=[], scheduledPayments=[],
                balances=dict(booked=balance, asOf=dt.datetime.combine(today, dt.time())))
    saved = dict(accountId='savings', type='savings', transactions=[], transactionDetails=[], pending=[],
                 standingOrders=[], directDebits=[], scheduledPayments=[], balances=dict(booked=savings))
    return dict(accounts=[main, saved], mainAccountId='main')


def check():
    with patch.object(model, 'season', return_value={m: 1.0 for m in range(1, 13)}):
        pic = picture()
        good = model.decide(pic, 100, monthly_savings=150)
        assert good['risk'] == 'none', good
        missed = model.decide(pic, 100, monthly_savings=250)
        assert missed['risk'] == 'savings' and missed['verdict'] == 'caution', missed
        assert missed['savings']['shortfall'] == 50
        assert good['everyday'] == missed['everyday']
        assert good['cashFlow'] == missed['cashFlow']  # Savings targets must not improve the risk forecast.
        assert missed['savings']['suggestedDailyBudget'] == 1.67
        over = model.decide(picture(600, 10000), 100, monthly_savings=0)
        assert over['risk'] == 'overdraft' and over['verdict'] == 'reconsider', over
        assert over['cashFlow']['forecastMonthEnd'] > 0  # Month-end alone would miss this warning.
        assert over['cashFlow']['lowestDate'] < over['cashFlow']['nextPayday']
        assert over['netWorth']['forecastEndWith'] > 10000  # Savings cannot hide an overdraft.
        assert over['cashFlow']['alreadyAtRisk']
        now = model.decide(picture(50), 100)
        assert now['cashFlow']['lowestWithPurchase'] < 0
        assert model.decide(pic, 100)['savings']['monthlyTarget'] == 0
        assert model.decide(pic, 100, goal_rate=.03)['savings']['monthlyTarget'] > 0
        for goal in (-1, True, '150', float('nan'), float('inf'), 1000001):
            try:
                model.decide(pic, 100, monthly_savings=goal)
            except ValueError:
                pass
            else:
                raise AssertionError(f'Invalid goal accepted: {goal}')
        try:
            model.decide(pic, 100, goal_rate=.03, monthly_savings=100)
        except ValueError:
            pass
        else:
            raise AssertionError('Two goal modes accepted')
        missing = copy.deepcopy(pic)
        for t in missing['accounts'][0]['transactions']:
            t['credit'] = 0
        assert model.decide(missing, 100)['verdict'] == 'neutral'
        # Pending rent must replace, not double, a predicted payment.
        pending = copy.deepcopy(pic)
        pending['accounts'][0]['pending'] = [dict(date=dt.date(2026, 4, 10), desc='RENT', debit=400, credit=0, mcc=None)]
        assert model.decide(pending, 100)['cashFlow'] == model.decide(pic, 100)['cashFlow']
        # An expected bill between the last booked transaction and snapshot is still reserved;
        # when it appears as pending it must not be counted twice.
        overdue = picture(today=dt.date(2026, 4, 12))
        posted_pending = copy.deepcopy(overdue)
        posted_pending['accounts'][0]['pending'] = [dict(date=dt.date(2026, 4, 10), desc='RENT', debit=400, credit=0, mcc=None)]
        a, b = model.decide(overdue, 100), model.decide(posted_pending, 100)
        assert a['cashFlow'] == b['cashFlow']
        assert a['netWorth']['forecastEndWith'] == b['netWorth']['forecastEndWith']
        # BNPL scheduled payments affect cash even though already deducted from net worth.
        scheduled = copy.deepcopy(pic)
        scheduled['accounts'][0]['scheduledPayments'] = [dict(date=dt.date(2026, 4, 15), amount=200, reference='KLARNA')]
        assert model.decide(scheduled, 100)['cashFlow']['forecastMonthEnd'] == good['cashFlow']['forecastMonthEnd'] - 200
        # A transfer into savings reduces current-account liquidity, not net worth.
        transfer = copy.deepcopy(pic)
        for month in (1, 2, 3):
            t = dict(date=dt.date(2026, month, 15), desc='SAVING', debit=200, credit=0, type='SO')
            transfer['accounts'][0]['transactions'].append(t)
            transfer['accounts'][0]['transactionDetails'].append(dict(mcc=None))
            transfer['accounts'][1]['transactions'].append(dict(t, debit=0, credit=200))
            transfer['accounts'][1]['transactionDetails'].append(dict(mcc=None))
        # The bank feed is chronological; preserve detail alignment when sorting.
        for a in transfer['accounts']:
            pairs = sorted(zip(a['transactions'], a['transactionDetails']), key=lambda x: x[0]['date'])
            a['transactions'] = [x[0] for x in pairs]
            a['transactionDetails'] = [x[1] for x in pairs]
        moved = model.decide(transfer, 100)
        assert moved['netWorth']['forecastEndWith'] == good['netWorth']['forecastEndWith']
        assert moved['cashFlow']['forecastMonthEnd'] == good['cashFlow']['forecastMonthEnd'] - 200
        # Forecast continues into the next month if payday is after month end.
        late = model.decide(picture(500, today=dt.date(2026, 4, 28)), 100)
        assert late['cashFlow']['horizon'] == '2026-05-25'
        # Pay in 3 checks every instalment, not just today's smaller debit.
        delayed = model.decide(picture(1500), 1500, payment_plan='pay_in_3')
        assert delayed['risk'] == 'overdraft', delayed
        assert delayed['cashFlow']['lowestDate'] >= '2026-06-01', delayed
        assert delayed['cashFlow']['horizon'] >= delayed['payments'][-1]['date']
        assert delayed['comparison']['payNow']['horizon'] == delayed['comparison']['payIn3']['horizon']
        spread = model.decide(picture(1000), 900, monthly_savings=150, payment_plan='pay_in_3')
        upfront = model.decide(picture(1000), 900, monthly_savings=150)
        assert upfront['risk'] == 'overdraft' and spread['risk'] == 'savings'
        assert spread['savings'] == upfront['savings']  # Outstanding debt still counts in full.
        purchase = model.decide(picture(1000), 153.07, payment_plan='pay_in_3')
        compare = purchase['comparison']
        assert round(compare['payIn3']['forecastMonthEnd'] - compare['payNow']['forecastMonthEnd'], 2) == 102.05
        assert [p['amount'] for p in purchase['payments']] == [51.02, 51.02, 51.03]

        schedule = model.purchase_payments(100, dt.date(2026, 1, 31), 'pay_in_3')
        assert [p['date'].isoformat() for p in schedule] == ['2026-01-31', '2026-02-28', '2026-03-31']
        assert [p['amount'] for p in schedule] == [33.33, 33.33, 33.34]
        try:
            model.decide(pic, 100, payment_plan='unknown')
        except ValueError:
            pass
        else:
            raise AssertionError('Unknown plan accepted')
        # More expensive purchases cannot improve a warning.
        ranks = {'good': 0, 'caution': 1, 'reconsider': 2}
        results = [model.decide(pic, p, monthly_savings=150) for p in (1, 100, 200, 1000, 3000)]
        assert sorted(ranks[d['verdict']] for d in results) == [ranks[d['verdict']] for d in results]
        json.dumps(results, allow_nan=False)
    print('Overdraft and savings checks passed.')


def integration():
    """Check the actual HTTP route on the committed sample bank customers (no generated cohort needed)."""
    import threading
    import urllib.request
    import urllib.error
    bank, base = model.start_bank()
    api = model.serve(0, quiet=True)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    def post(body):
        req = urllib.request.Request(f'http://127.0.0.1:{api.server_port}/decide',
            data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    try:
        ids = sorted({p.name[:10] for p in model.OB.glob('persona[0-9][0-9][0-9]_*.json')})
        assert ids, 'No sample bank files found'
        for pid in ids:
            body = dict(bank=dict(baseUrl=base, persona=pid), price=177.99, monthlySavings=150)
            now = post(body)
            spread = post(dict(body, paymentPlan='pay_in_3'))
            assert spread['savings'] == now['savings']
            assert round(sum(p['amount'] for p in spread['payments']), 2) == 177.99
            assert spread['cashFlow']['horizon'] >= spread['payments'][-1]['date']
            assert spread['comparison']['payNow']['horizon'] == spread['cashFlow']['horizon']
            print(pid, 'pay now:', now['risk'], 'pay in 3:', spread['risk'])
        for fields in [dict(monthlySavings=v) for v in (-1, True, '150', 1000001)] + [dict(paymentPlan='unknown'), dict(goalRate=.03)]:
            try:
                post(dict(body, **fields))
            except urllib.error.HTTPError as e:
                assert e.code == 400
            else:
                raise AssertionError(f'Invalid request accepted: {fields}')
    finally:
        api.shutdown()
        bank.shutdown()
    print(f'HTTP integration checks passed on {len(ids)} sample customers, both payment plans.')


if __name__ == '__main__':
    import sys
    check()
    if '--integration' in sys.argv:
        integration()

// Execute the real example hook with fake time and read-only workspace methods.
// This tests scheduling decisions, not a live Intent hook or messaging provider.
import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import { scheduleWatchdog } from '../examples/watchdog.mjs';

// Mirror Intent's persisted-state contract: count serialized UTF-8 bytes,
// retain the previous state when oversized, and round-trip accepted values.
function persistedState(previous, next) {
  if (next === undefined) return previous;
  if (next === null) return undefined;
  const serialized = JSON.stringify(next);
  return Buffer.byteLength(serialized, 'utf8') <= 16 * 1024
    ? JSON.parse(serialized) : previous;
}

async function fixture(ledgerChanges = {}, extraWorkers = [], initialState) {
  const reads = [];
  let definition;
  const ledger = {
    active: true,
    workers: [{ agentId: 'worker', noteId: 'task-note' }],
    outboxRevision: 1,
    ...ledgerChanges,
  };
  const worker = { status: 'active', note: 'Checking the requested options.' };
  const workers = [worker, ...extraWorkers];
  const ws = {
    hook: { async schedule(value) { definition = value; return { hookId: 'watchdog' }; } },
    note: {
      async read(id) {
        reads.push(['note.read', id]);
        if (id === 'ledger') return { rawContent: JSON.stringify(ledger) };
        const index = ledger.workers.findIndex(entry => entry.noteId === id);
        assert.ok(index >= 0);
        return { rawContent: workers[index].note };
      },
    },
    agent: {
      async status(id) {
        reads.push(['agent.status', id]);
        const index = ledger.workers.findIndex(entry => entry.agentId === id);
        assert.ok(index >= 0);
        return { status: workers[index].status };
      },
    },
  };
  await scheduleWatchdog(ws, 'ledger');
  let hookState = initialState;
  async function tick(now) {
    const context = vm.createContext({ ws, hookState, Date: { now: () => now } });
    const result = await vm.runInContext(`(async () => { ${definition.code} })()`, context);
    hookState = persistedState(hookState, result.state);
    return result;
  }
  return { definition, ledger, worker, workers, reads, tick, get state() { return hookState; } };
}

test('registers one bounded passive 30-second hook without creating agents', async () => {
  const f = await fixture();
  assert.equal(f.definition.delayMs, 30_000);
  assert.equal(f.definition.ttlMs, 3_600_000);
  assert.equal(f.definition.perpetual, true);
  assert.equal((await f.tick(0)).dispatch, false);
  assert.deepEqual(f.reads, [
    ['note.read', 'ledger'], ['agent.status', 'worker'], ['note.read', 'task-note'],
  ]);
  // ws has no send/create/delegate functions: calling any would fail this test.
});

test('first feedback occurs at 30 seconds and unchanged chatter is suppressed', async () => {
  const f = await fixture();
  assert.equal((await f.tick(0)).dispatch, false);
  assert.equal((await f.tick(29_999)).dispatch, false);
  assert.equal((await f.tick(30_000)).dispatch, true);
  assert.equal((await f.tick(60_000)).dispatch, false);
  assert.equal((await f.tick(90_000)).dispatch, false);
});

test('recent useful user feedback suppresses the first status update', async () => {
  const f = await fixture();
  await f.tick(0);
  f.ledger.lastUserFeedbackAt = 20_000;
  assert.equal((await f.tick(30_000)).dispatch, false);
});

test('completion and pending-delivery changes wake Ada once each', async () => {
  const f = await fixture();
  await f.tick(0);
  await f.tick(30_000);
  f.worker.status = 'idle';
  f.worker.note = 'Verified task outcome; final reply remains pending.';
  assert.equal((await f.tick(60_000)).dispatch, true);
  assert.equal((await f.tick(90_000)).dispatch, false);
  f.ledger.outboxRevision += 1;
  assert.equal((await f.tick(120_000)).dispatch, true);
  assert.equal((await f.tick(150_000)).dispatch, false);
});

test('quiet hours defer updates without losing meaningful changes', async () => {
  const f = await fixture({ quietUntil: 120_000 });
  await f.tick(0);
  f.worker.note = 'Found a viable option.';
  assert.equal((await f.tick(30_000)).dispatch, false);
  assert.equal((await f.tick(90_000)).dispatch, false);
  assert.equal((await f.tick(120_000)).dispatch, true);
  assert.equal((await f.tick(150_000)).dispatch, false);
});

test('still-working reminder is bounded to one', async () => {
  const f = await fixture();
  await f.tick(0);
  await f.tick(30_000);
  assert.equal((await f.tick(329_999)).dispatch, false);
  assert.equal((await f.tick(330_000)).dispatch, true);
  assert.equal((await f.tick(630_000)).dispatch, false);
  assert.equal((await f.tick(930_000)).dispatch, false);
});

test('renewal wakes the owner before expiration without repeated renewal chatter', async () => {
  const f = await fixture({ renewAt: 3_500_000 });
  await f.tick(0);
  const result = await f.tick(3_500_000);
  assert.equal(result.dispatch, true);
  assert.match(result.message, /renew/);
  const next = await f.tick(3_530_000);
  assert.ok(!next.dispatch || !/renew/.test(next.message));
});

test('finished work requests owner cleanup once and does not interrupt workers', async () => {
  const f = await fixture();
  await f.tick(0);
  f.ledger.active = false;
  const result = await f.tick(30_000);
  assert.equal(result.dispatch, true);
  assert.match(result.message, /final reply delivery/);
  assert.equal((await f.tick(60_000)).dispatch, false);
  assert.equal(f.reads.filter(([method]) => method === 'agent.status').length, 1);
});

test('restart uses persisted outbox and task ledger without sending anything', async () => {
  const f = await fixture({ outboxRevision: 8 });
  assert.equal((await f.tick(500_000)).dispatch, false);
  assert.equal((await f.tick(530_000)).dispatch, true);
  assert.deepEqual(new Set(f.reads.map(([method]) => method)), new Set(['note.read', 'agent.status']));
});


test('state harness measures serialized UTF-8 bytes and retains state on overflow', () => {
  const previous = { fingerprint: 'old' };
  assert.deepEqual(persistedState(previous, 'x'.repeat(16 * 1024 - 2)), 'x'.repeat(16 * 1024 - 2));
  assert.equal(persistedState(previous, 'x'.repeat(16 * 1024 - 1)), previous);
  assert.equal(persistedState(previous, '漢'.repeat(6_000)), previous);
  assert.equal(persistedState(previous, undefined), previous);
  assert.equal(persistedState(previous, null), undefined);
});

for (const [label, note, count] of [
  ['large ASCII', 'x'.repeat(17_000), 1],
  ['Unicode exceeding the byte cap but not the character cap', '🙂漢'.repeat(3_000), 1],
  ['multiple workers exceeding the cap together', 'private details '.repeat(250), 8],
]) {
  test(`${label}: persisted baseline, 30s feedback, dedup and late changes`, async () => {
    const workers = Array.from({ length: count }, (_, i) => ({ agentId: `worker-${i}`, noteId: `note-${i}` }));
    const f = await fixture({ workers }, Array.from({ length: count - 1 }, () => ({ status: 'active', note })));
    f.worker.note = note;
    const baseline = await f.tick(0);
    assert.equal(baseline.dispatch, false);
    assert.ok(f.state, 'baseline must survive the real serialized state cap');
    assert.ok(Buffer.byteLength(JSON.stringify(f.state), 'utf8') < 512);
    assert.ok(f.state.fingerprint.length < 128);
    assert.ok(!JSON.stringify(f.state).includes(note), 'raw private notes must not persist');
    const original = f.state.fingerprint;
    assert.equal((await f.tick(29_999)).dispatch, false);
    assert.equal((await f.tick(30_000)).dispatch, true);
    assert.equal((await f.tick(60_000)).dispatch, false);
    // Same length; only the last character of the last worker changes.
    f.workers.at(-1).note = note.slice(0, -1) + 'Z';
    assert.equal((await f.tick(90_000)).dispatch, true);
    assert.notEqual(f.state.fingerprint, original);
    assert.equal((await f.tick(120_000)).dispatch, false);
    f.workers.at(-1).status = 'idle';
    assert.equal((await f.tick(150_000)).dispatch, true);
    assert.equal((await f.tick(180_000)).dispatch, false);
    f.ledger.outboxRevision += 1;
    assert.equal((await f.tick(210_000)).dispatch, true);
    assert.equal((await f.tick(240_000)).dispatch, false);
    assert.ok(Buffer.byteLength(JSON.stringify(f.state), 'utf8') < 512);
  });
}

test('fingerprint distinguishes Unicode code units with matching low bytes', async () => {
  const f = await fixture();
  f.worker.note = 'Ā';
  await f.tick(0);
  await f.tick(30_000);
  const before = f.state.fingerprint;
  f.worker.note = 'Ȁ';
  assert.equal((await f.tick(60_000)).dispatch, true);
  assert.notEqual(f.state.fingerprint, before);
  assert.equal((await f.tick(90_000)).dispatch, false);
});

test('unchanged workers still wake for successive delivery retries and escalation', async () => {
  const f = await fixture({ lastUserFeedbackAt: 1 });
  await f.tick(0);
  for (const [version, dueAt] of [[1, 30_000], [2, 60_000], [3, 120_000], [4, 240_000]]) {
    f.ledger.delivery = { id: 'final-reply', version, dueAt };
    assert.equal((await f.tick(dueAt - 1)).dispatch, false);
    const result = await f.tick(dueAt);
    assert.equal(result.dispatch, true);
    assert.match(result.message, /delivery obligation/);
    assert.equal((await f.tick(dueAt + 1)).dispatch, false);
  }
  f.ledger.delivery = null;
  assert.equal((await f.tick(270_000)).dispatch, false);
});

test('due reconciliation bypasses quiet hours and unfinished final delivery prevents cleanup', async () => {
  const f = await fixture({ active: false, quietUntil: 600_000,
    delivery: { id: 'unknown-send', version: 1, dueAt: 60_000 } });
  assert.equal((await f.tick(0)).dispatch, false);
  assert.equal((await f.tick(30_000)).dispatch, false);
  const due = await f.tick(60_000);
  assert.equal(due.dispatch, true);
  assert.match(due.message, /delivery obligation/);
  assert.equal((await f.tick(90_000)).dispatch, false);
  f.ledger.delivery = null;
  assert.match((await f.tick(120_000)).message, /cancel/);
});

test('restart immediately discovers overdue delivery and recovers a lost owner wake', async () => {
  const f = await fixture({ quietUntil: 600_000,
    delivery: { id: 'pending-retry', version: 2, dueAt: 30_000 } });
  assert.equal((await f.tick(60_000)).dispatch, true);
  assert.equal((await f.tick(90_000)).dispatch, false);
  // No owner acknowledgement arrived: re-wake after a bounded 60-second lease.
  assert.equal((await f.tick(120_000)).dispatch, true);
  assert.equal((await f.tick(150_000)).dispatch, false);
  // Owner advances the durable obligation before doing work; a crash must not
  // lose that pending retry, even if no further outbox change ever occurs.
  f.ledger.delivery = { id: 'pending-retry', version: 3, dueAt: 210_000 };
  assert.equal((await f.tick(180_000)).dispatch, false);
  assert.equal((await f.tick(210_000)).dispatch, true);
  f.ledger.delivery = null;
  assert.equal((await f.tick(240_000)).dispatch, false);
});

test('large delivery identity is hashed and quiet progress remains deferred', async () => {
  const f = await fixture({ quietUntil: 180_000 });
  await f.tick(0);
  f.worker.note = 'Changed while quiet';
  f.ledger.delivery = { id: '🔐'.repeat(10_000), version: 'v'.repeat(20_000), dueAt: 30_000 };
  const result = await f.tick(30_000);
  assert.equal(result.dispatch, true);
  assert.match(result.message, /delivery obligation/);
  assert.ok(Buffer.byteLength(JSON.stringify(f.state), 'utf8') < 512);
  f.ledger.delivery = null;
  assert.equal((await f.tick(60_000)).dispatch, false);
  assert.equal((await f.tick(180_000)).dispatch, true);
  assert.equal((await f.tick(210_000)).dispatch, false);
});


test('persisted wake lease survives restart and cannot consume a future deadline', async () => {
  const ledger = { quietUntil: 600_000, delivery: { id: 'final', version: 1, dueAt: 30_000 } };
  const first = await fixture(ledger);
  await first.tick(0);
  await first.tick(30_000);
  const resumed = await fixture(ledger, [], JSON.parse(JSON.stringify(first.state)));
  assert.equal((await resumed.tick(60_000)).dispatch, false);
  assert.equal((await resumed.tick(90_000)).dispatch, true);
  resumed.ledger.delivery = { id: 'final', version: 2, dueAt: 180_000 };
  const future = await resumed.tick(120_000);
  assert.equal(future.dispatch, false);
  const restarted = await fixture(resumed.ledger, [], future.state);
  assert.equal((await restarted.tick(150_000)).dispatch, false);
  assert.equal((await restarted.tick(180_000)).dispatch, true);
});

test('ongoing due delivery does not starve watchdog renewal', async () => {
  const f = await fixture({ renewAt: 60_000 });
  await f.tick(0);
  f.ledger.delivery = { id: 'final', version: 1, dueAt: 30_000 };
  assert.match((await f.tick(30_000)).message, /delivery obligation/);
  f.ledger.delivery = { id: 'final', version: 2, dueAt: 60_000 };
  assert.match((await f.tick(60_000)).message, /renew/);
  assert.match((await f.tick(90_000)).message, /delivery obligation/);
});

test('fingerprint uses fixed-width unsigned FNV-1a output when its high bit is set', async () => {
  const f = await fixture({ outboxRevision: 2 });
  f.worker.status = 'idle';
  f.worker.note = 'Verified task outcome; final reply remains pending.';
  const result = await f.tick(0);
  assert.equal(result.state.fingerprint, '964ae52414e9ce25');
});

/** Copy this function into an Intent workspace_api call to use it there.
 * No hook is registered by importing this module. Run as Ada, the reply owner.
 * ledgerNoteId is a private JSON note: see docs/operations.md for its schema.
 */
export async function scheduleWatchdog(ws, ledgerNoteId) {
  return ws.hook.schedule({
    name: "Assistant progress and delivery",
    delayMs: 30_000,
    ttlMs: 3_600_000,
    perpetual: true,
    code: `
const ledger = JSON.parse((await ws.note.read(${JSON.stringify(ledgerNoteId)})).rawContent);
const now = Date.now();
const previous = hookState || {};
if (!ledger.active && !ledger.delivery) {
  if (previous.stopped) return { dispatch: false };
  return { dispatch: true, message: "Work finished; cancel this watchdog after checking final reply delivery.", state: { stopped: true } };
}
const snapshots = await Promise.all((ledger.active ? ledger.workers || [] : []).map(async worker => {
  const [agent, note] = await Promise.all([
    ws.agent.status(worker.agentId), ws.note.read(worker.noteId),
  ]);
  return [worker.agentId, agent.status, note.rawContent];
}));
// FNV-1a over both bytes of every UTF-16 code unit. This is a compact change
// detector, not a security hash. Keep raw notes out of persisted hook state.
function fingerprintOf(value) {
  const serialized = JSON.stringify(value);
  // Use exact 32-bit limbs: no Node globals or engine-specific BigInt behavior.
  let high = 0xcbf29ce4;
  let low = 0x84222325;
  for (let i = 0; i < serialized.length; i++) {
    const unit = serialized.charCodeAt(i);
    for (let shift = 0; shift <= 8; shift += 8) {
      low = (low ^ ((unit >>> shift) & 255)) >>> 0;
      // Multiply by 0x100000001b3 modulo 2^64. Each intermediate is < 2^53.
      const product = low * 435;
      high = (high * 435 + low * 256 + Math.floor(product / 0x100000000)) >>> 0;
      low = product >>> 0;
    }
  }
  return high.toString(16).padStart(8, "0") + low.toString(16).padStart(8, "0");
}
const fingerprint = fingerprintOf([snapshots, ledger.outboxRevision]);
const baseline = hookState || { fingerprint, started: now, lastDispatch: now, reminded: false };
// Delivery wakes do not consume deferred progress or its feedback/reminder clock.
const delivery = ledger.delivery;
const deliveryFingerprint = delivery ? fingerprintOf([delivery.id, delivery.version, delivery.dueAt]) : null;
const state = { ...baseline };
if (state.deliveryFingerprint !== deliveryFingerprint) {
  state.deliveryFingerprint = deliveryFingerprint;
  delete state.deliveryDispatchedAt;
}
if (hookState && ledger.renewAt && now >= ledger.renewAt && !previous.renewalNotified) {
  return { dispatch: true, message: "Reconcile the durable watch ledger and renew this authorized watchdog before expiry.", state: { ...state, renewalNotified: true } };
}
if (delivery && now >= delivery.dueAt &&
    (state.deliveryDispatchedAt === undefined || now - state.deliveryDispatchedAt >= 60_000)) {
  return {
    dispatch: true,
    message: "Process the due delivery obligation from the durable ledger; reconcile before retrying, persist the next deadline, and escalate if required. This is internal work, not a progress message.",
    state: { ...state, deliveryDispatchedAt: now },
  };
}
if (!hookState) return { dispatch: false, state };
if (!ledger.active || now < (ledger.quietUntil || 0)) return { dispatch: false, state };
const firstFeedback = !previous.feedbackNotified && now - previous.started >= 30_000 &&
  (ledger.lastUserFeedbackAt || 0) <= previous.started;
const changed = fingerprint !== previous.fingerprint;
const reminder = !previous.reminded && now - previous.lastDispatch >= 300_000 &&
  (ledger.lastUserFeedbackAt || 0) <= previous.lastDispatch;
if (now - previous.lastDispatch < 30_000 || !(firstFeedback || changed || reminder)) {
  return { dispatch: false, state };
}
return {
  dispatch: true,
  message: "Review passive worker snapshots and the final-reply outbox; send only useful, deduplicated feedback through the selected channel.",
  state: { ...state, fingerprint, lastDispatch: now, feedbackNotified: true, reminded: previous.reminded || reminder },
};`,
  });
}

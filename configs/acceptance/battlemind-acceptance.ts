/** BattleMind acceptance-evidence-1. Observer only: no simulator mutation or RNG. */
import * as fs from 'node:fs';
import * as path from 'node:path';
import {createHash} from 'node:crypto';

const SCHEMA = 'bm-acceptance-1';
const rooms = new WeakMap<object, any>();
const battles = new WeakMap<object, any>();
const envelopes = new WeakMap<object, any>();
const digest = (s: string) => createHash('sha256').update(s, 'utf8').digest('hex');
export function canonical(value: any): string {
	if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
	if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
	return JSON.stringify(value);
}
function config() {
	const root = process.env.BATTLEMIND_ACCEPTANCE_DIR;
	const session = process.env.BATTLEMIND_ACCEPTANCE_SESSION;
	const build = process.env.BATTLEMIND_ACCEPTANCE_BUILD;
	if (!root || !path.isAbsolute(root) || !/^[a-f0-9]{32}$/.test(session || '') || !/^[a-f0-9]{64}$/.test(build || '')) return null;
	return {root, session, build};
}
// Swallow only instrumentation errors. A broken/missing/truncated/unsealed trace
// is rejected offline; recording failure must not alter engine returns or RNG.
function observe(fn: () => void) { try { fn(); } catch {} }
class Writer {
	fd: number; n = 0; prev = '0'.repeat(64); broken = false; closed = false;
	constructor(readonly room: string, readonly channel: string) {
		const c = config()!;
		if (!/^battle-gen1ou-[a-z0-9-]+$/.test(room)) throw new Error('Unsupported room');
		this.fd = fs.openSync(path.join(c.root, `${room}.${channel}.jsonl`), 'wx', 0o600);
		this.event('open', {channel});
	}
	event(kind: string, fields: any = {}) {
		if (this.closed || this.broken) return;
		try {
			const c = config()!;
			const body = JSON.stringify({schema: SCHEMA, session: c.session, build: c.build, room: this.room, kind, ...fields});
			const hash = digest(this.prev + '\n' + body);
			const bytes = Buffer.from(JSON.stringify({seq: this.n + 1, prev: this.prev, body, hash}) + '\n');
			if (fs.writeSync(this.fd, bytes) !== bytes.length) throw new Error('Partial evidence write');
			this.n++; this.prev = hash;
		} catch { this.broken = true; }
	}
	close() {
		if (this.closed) return;
		this.event('close', {complete: true}); this.closed = true;
		observe(() => fs.closeSync(this.fd));
	}
}
function roomState(room: any) {
	let state = rooms.get(room);
	if (!state) { state = {writer: new Writer(room.room.roomid, 'room'), current: null}; rooms.set(room, state); }
	return state;
}
function battleState(battle: any) {
	let state = battles.get(battle);
	if (!state) { state = {writer: null, buffer: [], requests: {}, pending: {}, current: null}; battles.set(battle, state); }
	return state;
}
function event(state: any, kind: string, fields: any = {}) {
	if (state.writer) state.writer.event(kind, fields);
	else if (state.buffer.length < 64) state.buffer.push([kind, fields]);
	else state.broken = true;
}
export function roomRequest(room: any, side: string, raw: string) {
	if (!config()) return;
	observe(() => roomState(room).writer.event('request', {side, rqid: JSON.parse(raw).rqid, request_sha256: digest(raw)}));
}
export function roomCall(room: any, user: any, data: string, operation: string, fn: () => any) {
	if (!config()) return fn();
	let state: any;
	observe(() => {
		state = roomState(room);
		const player = room.playerTable[user.id]; const request = player?.request;
		const parts = data.split('|');
		state.current = {side: player?.slot || null, attempt: parts[2] || null,
			rqid: /^\d+$/.test(parts[1] || '') ? Number(parts[1]) : null,
			current_rqid: request?.rqid ?? null, request_sha256: request?.request ? digest(request.request) : null,
			command: parts[0], operation, forwarded: false};
		state.writer.event('received', state.current);
	});
	try { return fn(); } finally {
		observe(() => { if (state?.current && !state.current.forwarded) state.writer.event('room_rejected', state.current); if (state) state.current = null; });
	}
}
export function forward(room: any, side: string, command: string): string {
	const ordinary = `>${side} ${command}`;
	if (!config()) return ordinary;
	let result = ordinary;
	observe(() => {
		const state = roomState(room); const current = state.current;
		if (!current) { state.writer.event('unbound_forward', {side}); return; }
		current.forwarded = true;
		const context = {...current, room: room.room.roomid, session: config()!.session, build: config()!.build};
		state.writer.event('forwarded', current);
		result = `>bmaccept ${JSON.stringify(context)}\n${ordinary}`;
	});
	return result;
}
export function envelope(stream: any, text: string) {
	if (!config()) return;
	observe(() => { envelopes.set(stream, JSON.parse(text)); });
}
export function input(stream: any, side: string, command: string, fn: () => any) {
	if (!config()) return fn();
	let state: any;
	observe(() => {
		state = battleState(stream.battle); const context = envelopes.get(stream); envelopes.delete(stream);
		if (!state.writer && context?.room) {
			state.writer = new Writer(context.room, 'sim');
			for (const [kind, data] of state.buffer) state.writer.event(kind, data);
			state.buffer = []; if (state.broken) state.writer.event('fault', {reason: 'buffer_overflow'});
		}
		state.current = context && context.side === side && (context.operation === 'undo' ? command === 'undo' : context.command === command) ? context : null;
		if (!state.current) event(state, 'unbound_input', {side});
		else event(state, 'dispatch', {...context, engine_request: state.requests[side] || null});
	});
	try { return fn(); } finally {
		observe(() => { if (state?.current) event(state, 'dispatch_end', {attempt: state.current.attempt}); if (state) state.current = null; });
	}
}
export function engineRequest(side: any, update: any) {
	if (!config()) return;
	observe(() => {
		const state = battleState(side.battle);
		const req = {epoch: (state.requests[side.id]?.epoch || 0) + 1, sha256: digest(canonical(update))};
		state.requests[side.id] = req; event(state, 'engine_request', {side: side.id, ...req});
	});
}
export function parsed(battle: any, side: any, ok: boolean) {
	if (!config()) return;
	observe(() => {
		const state = battleState(battle); const previous = state.pending[side.id];
		if (previous && previous.choice !== side.choice) {
			event(state, 'replaced', {side: side.id, attempt: previous.attempt, by: state.current?.attempt || null}); delete state.pending[side.id];
		}
		event(state, 'parsed', {side: side.id, attempt: state.current?.attempt || null, ok});
	});
}
export function branch(side: any, reason: string) {
	if (!config()) return;
	observe(() => { const state = battleState(side.battle); event(state, 'normalization', {side: side.id, attempt: state.current?.attempt || null, reason}); });
}
export function choiceError(side: any, reason: string) {
	if (!config()) return;
	observe(() => { const state = battleState(side.battle); event(state, 'choice_error', {side: side.id, attempt: state.current?.attempt || null, reason}); });
}
function actionView(side: any) {
	return side.choice.actions.map((a: any) => ({kind: a.choice, move_id: a.moveid ?? null,
		move_slot: a.moveSlot ?? null, target_location: a.targetLoc ?? null,
		switch_position: ['switch', 'instaswitch'].includes(a.choice) ? a.target.position + 1 : null}));
}
export function accepted(battle: any, side: any) {
	if (!config()) return;
	observe(() => {
		const state = battleState(battle); const attempt = state.current?.attempt || null;
		event(state, 'accepted', {side: side.id, attempt, choice: side.getChoice(), actions: actionView(side)});
		state.pending[side.id] = {attempt, choice: side.choice};
	});
}
export function committed(battle: any, side: any, choice: string, index: number) {
	if (!config()) return;
	observe(() => {
		const state = battleState(battle); const pending = state.pending[side.id];
		event(state, 'committed', {side: side.id, attempt: pending?.choice === side.choice ? pending.attempt : null,
			choice, input_index: index, actions: actionView(side)});
		delete state.pending[side.id];
	});
}
export function cancelled(battle: any, side: any) {
	if (!config()) return;
	observe(() => {
		const state = battleState(battle); const pending = state.pending[side.id];
		event(state, 'cancelled', {side: side.id, attempt: pending?.attempt || null, by: state.current?.attempt || null});
		delete state.pending[side.id];
	});
}
export function engineEnd(stream: any) { if (config()) observe(() => battleState(stream.battle).writer?.close()); }
export function roomEnd(room: any) { if (config()) observe(() => roomState(room).writer.close()); }

#!/usr/bin/env node
/**
 * crypto.js — Node WASM bridge for pw_raze.wasm
 */

const fs = require('fs');
const crypto = require('crypto');
const path = require('path');

const WASM_PATH = path.join(__dirname, 'pw_raze.wasm');
let W = null;

function buildInput(p, q, r) {
    const pb = Buffer.from(p, 'utf8');
    const qb = Buffer.from(q, 'utf8');
    const rb = Buffer.from(r, 'utf8');
    const h = Buffer.alloc(12);
    h.writeUInt32BE(pb.length, 0);
    h.writeUInt32BE(qb.length, 4);
    h.writeUInt32BE(rb.length, 8);
    return Buffer.concat([h, pb, qb, rb]);
}

function callWasm(fnName, p, q, payload) {
    const input = buildInput(p, q, payload);
    const inPtr = W.a(input.length);
    new Uint8Array(W.memory.buffer, inPtr, input.length).set(input);
    const resPtr = W[fnName](inPtr, input.length);
    if (resPtr === 0) throw new Error(`${fnName}() returned 0`);
    const resLen = W.e(resPtr);
    const out = new TextDecoder().decode(
        new Uint8Array(W.memory.buffer, resPtr + 4, resLen)
    );
    try { W.b(inPtr, input.length); } catch {}
    try { W.f(resPtr); } catch {}
    return out;
}

async function initWasm() {
    if (W) return W;
    const bytes = fs.readFileSync(WASM_PATH);
    let inst = null;
    const imports = {
        env: {
            r(ptr, size) {
                try {
                    const mem = new Uint8Array(inst.exports.memory.buffer, ptr, size);
                    for (let i = 0; i < size; i += 65536) {
                        crypto.randomFillSync(mem.subarray(i, Math.min(i + 65536, size)));
                    }
                    return 0;
                } catch { return 1; }
            }
        }
    };
    const result = await WebAssembly.instantiate(bytes, imports);
    inst = result.instance;
    W = inst.exports;
    return W;
}

async function main() {
    let input = '';
    process.stdin.setEncoding('utf8');
    for await (const chunk of process.stdin) input += chunk;

    try {
        const req = JSON.parse(input);
        await initWasm();
        const payload = typeof req.data === 'string' ? req.data : JSON.stringify(req.data);
        const result = callWasm(req.op === 'encrypt' ? 'c' : 'd', req.jti, req.uid, payload);
        let parsed;
        try { parsed = JSON.parse(result); } catch { parsed = result; }
        process.stdout.write(JSON.stringify({ ok: true, result: parsed }));
    } catch (e) {
        process.stdout.write(JSON.stringify({ ok: false, error: e.message }));
        process.exit(1);
    }
}

main();

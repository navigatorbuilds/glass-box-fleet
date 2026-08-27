/* @ts-self-types="./elara_verify_wasm.d.ts" */

/**
 * Verify a mandate **bundle** entirely offline — the accountability/authority-
 * to-act differentiator (who/which-AI-agent was *authorized* to do what, by
 * whom, valid at signing — or revoked) that OpenTimestamps and a bare PQ
 * signature structurally cannot express.
 *
 * Input is a JSON envelope `{bundle_version, act, mandates[], revocations[]}`
 * of SIGNED carrier records (see `examples/verify/sample-mandate-bundles.json`).
 * This is a thin shell over the shared, drift-proof
 * [`crate::mandate_bundle::evaluate_mandate_bundle`] — the SAME pure
 * verdict core the live node's `GET /mandate/status` calls — so the browser
 * verdict can never diverge from the node verdict.
 *
 * Returns a JS object (see `BundleVerdict`): `{verdict, glyph, flag,
 * authorized, attributes_to_principal, network, signer, principal,
 * act_timestamp_ms, explanation, lineage[], scope_note, scope_deferred,
 * soundness_caveats[], checks[], reason}`. `scope_deferred` is `true`/`false`
 * once a leaf mandate resolved (non-wildcard vs wildcard scope — neither
 * means scope was CHECKED; v0 defers enforcement), `null` when none was.
 * Never throws — malformed input is `verdict: "FAILED"`.
 *
 * HONEST SCOPE: a `✓ CONSISTENT` verdict proves signatures + that authority
 * held at the act's signed time GIVEN THE RECORDS IN THIS BUNDLE. It does NOT
 * prove the records are on-chain / sealed / time-anchored, and cannot detect a
 * revocation the bundle author withheld — hence the verdict is `CONSISTENT`,
 * never the node-only `AUTHORIZED`, and `soundness_caveats` ship on every
 * judged verdict (empty only on input-error `FAILED`, where nothing was
 * verified).
 * @param {string} bundle_json
 * @returns {any}
 */
export function evaluate_mandate_bundle(bundle_json) {
    const ptr0 = passStringToWasm0(bundle_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.evaluate_mandate_bundle(ptr0, len0);
    return ret;
}

/**
 * Verify a `.elara-receipt` v1 envelope entirely offline — the FULL chain
 * (record → inclusion proof → epoch seal → anchor, plus account
 * inclusion/exclusion legs) in one pasted file, graded through the SAME
 * shared [`crate::grade`] sequence as `elara-verify --receipt`, so the
 * browser verdict can never drift from the CLI verdict.
 *
 * `receipt_json` is the envelope text (a bare record is accepted as the
 * degenerate case, exactly like the CLI). `pins_json` carries the
 * verifier-side trust pins `{"trusted_anchor": ["<pubkey-hex>", …],
 * "expected_hash": "…", "expect_root": "…", "expect_identity": "…"}` — all
 * optional (pass `""` or `"{}"` for none), STRICTLY parsed (an unknown key
 * refuses — pins are trust-affecting), and NEVER read from the receipt
 * itself: a receipt cannot vouch for its own trust root, so pin-less runs
 * grade PARTIAL, never a false green.
 *
 * Returns `{verdict, glyph, checks[], reason, producer, not_evaluated[]}`.
 * Never throws — malformed input surfaces as `verdict: "FAILED"` with the
 * reason (the CLI's exit-2 analog). `producer` is self-declared metadata:
 * display it with a provenance caveat; no check vouches for it.
 * @param {string} receipt_json
 * @param {string} pins_json
 * @returns {any}
 */
export function verify_receipt_offline(receipt_json, pins_json) {
    const ptr0 = passStringToWasm0(receipt_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(pins_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    const ret = wasm.verify_receipt_offline(ptr0, len0, ptr1, len1);
    return ret;
}

/**
 * Verify a pasted `ValidationRecord` JSON entirely offline.
 *
 * Mirrors the record leg of `elara-verify <record.json>`: structure parse,
 * identity binding (the embedded public key must SHA3-256 to the claimed
 * identity), and the Dilithium3 (ML-DSA-65) signature over the record's
 * canonical `signable_bytes()`.
 *
 * Returns a JS object
 * `{verdict, glyph, checks: [{name, status, glyph, detail}], reason}`.
 * Never throws — a malformed input surfaces as `verdict: "FAILED"` with the
 * parse reason, not an exception. (Same export NAME as the legacy copy in
 * `browser-node/src/verify_record.rs`, but the result shapes have DRIFTED —
 * this one adds `headline`. The demo pages build against THIS crate (ci.yml
 * verify-wasm job); do not switch bundles without re-checking the consuming
 * JS. 2026-07-12 sweep A8.)
 * @param {string} record_json
 * @returns {any}
 */
export function verify_record_offline(record_json) {
    const ptr0 = passStringToWasm0(record_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.verify_record_offline(ptr0, len0);
    return ret;
}
function __wbg_get_imports() {
    const import0 = {
        __proto__: null,
        __wbg_Error_fdd633d4bb5dd76a: function(arg0, arg1) {
            const ret = Error(getStringFromWasm0(arg0, arg1));
            return ret;
        },
        __wbg___wbindgen_is_string_1fca8072260dd261: function(arg0) {
            const ret = typeof(arg0) === 'string';
            return ret;
        },
        __wbg___wbindgen_throw_ea4887a5f8f9a9db: function(arg0, arg1) {
            throw new Error(getStringFromWasm0(arg0, arg1));
        },
        __wbg_new_2e117a478906f062: function() {
            const ret = new Object();
            return ret;
        },
        __wbg_new_3444eb7412549f0b: function() {
            const ret = new Map();
            return ret;
        },
        __wbg_new_36e147a8ced3c6e0: function() {
            const ret = new Array();
            return ret;
        },
        __wbg_set_6be42768c690e380: function(arg0, arg1, arg2) {
            arg0[arg1] = arg2;
        },
        __wbg_set_9a1d61e17de7054c: function(arg0, arg1, arg2) {
            const ret = arg0.set(arg1, arg2);
            return ret;
        },
        __wbg_set_dc601f4a69da0bc2: function(arg0, arg1, arg2) {
            arg0[arg1 >>> 0] = arg2;
        },
        __wbindgen_cast_0000000000000001: function(arg0) {
            // Cast intrinsic for `F64 -> Externref`.
            const ret = arg0;
            return ret;
        },
        __wbindgen_cast_0000000000000002: function(arg0) {
            // Cast intrinsic for `I64 -> Externref`.
            const ret = arg0;
            return ret;
        },
        __wbindgen_cast_0000000000000003: function(arg0, arg1) {
            // Cast intrinsic for `Ref(String) -> Externref`.
            const ret = getStringFromWasm0(arg0, arg1);
            return ret;
        },
        __wbindgen_cast_0000000000000004: function(arg0) {
            // Cast intrinsic for `U64 -> Externref`.
            const ret = BigInt.asUintN(64, arg0);
            return ret;
        },
        __wbindgen_init_externref_table: function() {
            const table = wasm.__wbindgen_externrefs;
            const offset = table.grow(4);
            table.set(0, undefined);
            table.set(offset + 0, undefined);
            table.set(offset + 1, null);
            table.set(offset + 2, true);
            table.set(offset + 3, false);
        },
    };
    return {
        __proto__: null,
        "./elara_verify_wasm_bg.js": import0,
    };
}

function getStringFromWasm0(ptr, len) {
    return decodeText(ptr >>> 0, len);
}

let cachedUint8ArrayMemory0 = null;
function getUint8ArrayMemory0() {
    if (cachedUint8ArrayMemory0 === null || cachedUint8ArrayMemory0.byteLength === 0) {
        cachedUint8ArrayMemory0 = new Uint8Array(wasm.memory.buffer);
    }
    return cachedUint8ArrayMemory0;
}

function passStringToWasm0(arg, malloc, realloc) {
    if (realloc === undefined) {
        const buf = cachedTextEncoder.encode(arg);
        const ptr = malloc(buf.length, 1) >>> 0;
        getUint8ArrayMemory0().subarray(ptr, ptr + buf.length).set(buf);
        WASM_VECTOR_LEN = buf.length;
        return ptr;
    }

    let len = arg.length;
    let ptr = malloc(len, 1) >>> 0;

    const mem = getUint8ArrayMemory0();

    let offset = 0;

    for (; offset < len; offset++) {
        const code = arg.charCodeAt(offset);
        if (code > 0x7F) break;
        mem[ptr + offset] = code;
    }
    if (offset !== len) {
        if (offset !== 0) {
            arg = arg.slice(offset);
        }
        ptr = realloc(ptr, len, len = offset + arg.length * 3, 1) >>> 0;
        const view = getUint8ArrayMemory0().subarray(ptr + offset, ptr + len);
        const ret = cachedTextEncoder.encodeInto(arg, view);

        offset += ret.written;
        ptr = realloc(ptr, len, offset, 1) >>> 0;
    }

    WASM_VECTOR_LEN = offset;
    return ptr;
}

let cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
cachedTextDecoder.decode();
const MAX_SAFARI_DECODE_BYTES = 2146435072;
let numBytesDecoded = 0;
function decodeText(ptr, len) {
    numBytesDecoded += len;
    if (numBytesDecoded >= MAX_SAFARI_DECODE_BYTES) {
        cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
        cachedTextDecoder.decode();
        numBytesDecoded = len;
    }
    return cachedTextDecoder.decode(getUint8ArrayMemory0().subarray(ptr, ptr + len));
}

const cachedTextEncoder = new TextEncoder();

if (!('encodeInto' in cachedTextEncoder)) {
    cachedTextEncoder.encodeInto = function (arg, view) {
        const buf = cachedTextEncoder.encode(arg);
        view.set(buf);
        return {
            read: arg.length,
            written: buf.length
        };
    };
}

let WASM_VECTOR_LEN = 0;

let wasmModule, wasmInstance, wasm;
function __wbg_finalize_init(instance, module) {
    wasmInstance = instance;
    wasm = instance.exports;
    wasmModule = module;
    cachedUint8ArrayMemory0 = null;
    wasm.__wbindgen_start();
    return wasm;
}

async function __wbg_load(module, imports) {
    if (typeof Response === 'function' && module instanceof Response) {
        if (typeof WebAssembly.instantiateStreaming === 'function') {
            try {
                return await WebAssembly.instantiateStreaming(module, imports);
            } catch (e) {
                const validResponse = module.ok && expectedResponseType(module.type);

                if (validResponse && module.headers.get('Content-Type') !== 'application/wasm') {
                    console.warn("`WebAssembly.instantiateStreaming` failed because your server does not serve Wasm with `application/wasm` MIME type. Falling back to `WebAssembly.instantiate` which is slower. Original error:\n", e);

                } else { throw e; }
            }
        }

        const bytes = await module.arrayBuffer();
        return await WebAssembly.instantiate(bytes, imports);
    } else {
        const instance = await WebAssembly.instantiate(module, imports);

        if (instance instanceof WebAssembly.Instance) {
            return { instance, module };
        } else {
            return instance;
        }
    }

    function expectedResponseType(type) {
        switch (type) {
            case 'basic': case 'cors': case 'default': return true;
        }
        return false;
    }
}

function initSync(module) {
    if (wasm !== undefined) return wasm;


    if (module !== undefined) {
        if (Object.getPrototypeOf(module) === Object.prototype) {
            ({module} = module)
        } else {
            console.warn('using deprecated parameters for `initSync()`; pass a single object instead')
        }
    }

    const imports = __wbg_get_imports();
    if (!(module instanceof WebAssembly.Module)) {
        module = new WebAssembly.Module(module);
    }
    const instance = new WebAssembly.Instance(module, imports);
    return __wbg_finalize_init(instance, module);
}

async function __wbg_init(module_or_path) {
    if (wasm !== undefined) return wasm;


    if (module_or_path !== undefined) {
        if (Object.getPrototypeOf(module_or_path) === Object.prototype) {
            ({module_or_path} = module_or_path)
        } else {
            console.warn('using deprecated parameters for the initialization function; pass a single object instead')
        }
    }

    if (module_or_path === undefined) {
        module_or_path = new URL('elara_verify_wasm_bg.wasm', import.meta.url);
    }
    const imports = __wbg_get_imports();

    if (typeof module_or_path === 'string' || (typeof Request === 'function' && module_or_path instanceof Request) || (typeof URL === 'function' && module_or_path instanceof URL)) {
        module_or_path = fetch(module_or_path);
    }

    const { instance, module } = await __wbg_load(await module_or_path, imports);

    return __wbg_finalize_init(instance, module);
}

export { initSync, __wbg_init as default };

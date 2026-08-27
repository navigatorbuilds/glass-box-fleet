//! glass-box-sealer — seals one agent action-event into a signed, hash-linked
//! evidence record in the published `elara-record` wire format (ML-DSA-65 /
//! FIPS 204 signatures).
//!
//! Honesty note (binding): the output is a **signed, hash-linked evidence
//! log** — offline-verifiable evidence integrity. It is NOT a blockchain, not
//! consensus-sealed, and makes no authorization claim by itself.
//!
//! Seal mode (default):
//!   echo '{"agent":"buyer-1","action":"create_po","params":{...},"ts":...}' \
//!     | glass-box-sealer [--prev <64-hex>]
//! reads ONE JSON action-event on stdin, creates + signs a record whose
//! content binds sha3-256(canonical event) + the previous record's hash
//! (all-zero hash for the first record of a run), and prints
//! `{"record_hash": "...", "record": {...}}` on stdout — append the lines to
//! a file and you have the run's chain.
//!
//! Verify mode:
//!   glass-box-sealer --verify-chain <chain.jsonl>
//! recomputes every link (record hash, signature over the signed preimage via
//! elara-record's own `dilithium3_verify`, content↔metadata binding, prev
//! pointer continuity) and exits 1 naming the first broken record.
//!
//! Identity: loaded from the JSON file at `SEALER_IDENTITY` (default
//! `./sealer-identity.json`); a fresh demo identity is generated there if the
//! file is absent. The file holds a plaintext demo secret key — it is
//! gitignored and must never be committed; deployments inject it as a secret.

use std::collections::BTreeMap;
use std::io::Read;
use std::process::ExitCode;

use dilithium::params::DilithiumMode;
use dilithium::safe_api::DilithiumKeyPair;
use elara_record::hash::sha3_256;
use elara_record::pqc::dilithium3_verify;
use elara_record::record::{Classification, ValidationRecord};
use serde::{Deserialize, Serialize};

const MODE: DilithiumMode = DilithiumMode::Dilithium3;
const GENESIS_PREV: &str =
    "0000000000000000000000000000000000000000000000000000000000000000";
/// Network binding stamped into every sealed record (v6+ signed preimage).
/// Deliberately NOT any production network's id: these records are demo
/// evidence for the glass-box fleet and say so on the wire.
const DEMO_NETWORK_ID: &str = "glass-box-demo";

/// The action-event contract: exactly what an agent tool-hop reports.
/// Field order is the canonical serialization order (struct-order serde),
/// and `params` objects serialize with sorted keys (serde_json's default
/// BTreeMap backing) — so the event hash is stable across re-serialization.
/// `ts` is whatever the emitter uses (ISO-8601 string from the fleet wrapper,
/// or a number) — it is evidence content, not something the sealer interprets.
#[derive(Serialize, Deserialize)]
struct ActionEvent {
    agent: String,
    action: String,
    params: serde_json::Value,
    ts: serde_json::Value,
}

/// What binds the chain: the record's content bytes are exactly this,
/// canonically serialized — so `content_hash` commits to BOTH the event and
/// the previous record under the ML-DSA-65 signature.
#[derive(Serialize, Deserialize)]
struct ContentBinding {
    event_hash: String,
    prev_record_hash: String,
}

#[derive(Serialize, Deserialize)]
struct SealedLine {
    record_hash: String,
    record: ValidationRecord,
}

#[derive(Serialize, Deserialize)]
struct IdentityFile {
    algorithm: String,
    public_key_hex: String,
    secret_key_hex: String,
}

fn load_or_generate_identity(path: &str) -> Result<DilithiumKeyPair, String> {
    match std::fs::read_to_string(path) {
        Ok(text) => {
            let id: IdentityFile = serde_json::from_str(&text)
                .map_err(|e| format!("identity file {path}: bad JSON: {e}"))?;
            if id.algorithm != "ML-DSA-65" {
                return Err(format!(
                    "identity file {path}: unsupported algorithm {:?} (expected ML-DSA-65)",
                    id.algorithm
                ));
            }
            let pk = hex::decode(&id.public_key_hex)
                .map_err(|e| format!("identity file {path}: bad public_key_hex: {e}"))?;
            let sk = hex::decode(&id.secret_key_hex)
                .map_err(|e| format!("identity file {path}: bad secret_key_hex: {e}"))?;
            DilithiumKeyPair::from_keys(&sk, &pk, MODE)
                .map_err(|e| format!("identity file {path}: key validation failed: {e:?}"))
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            let kp = DilithiumKeyPair::generate(MODE)
                .map_err(|e| format!("demo identity generation failed: {e:?}"))?;
            let id = IdentityFile {
                algorithm: "ML-DSA-65".to_string(),
                public_key_hex: hex::encode(kp.public_key()),
                secret_key_hex: hex::encode(kp.private_key()),
            };
            let text = serde_json::to_string_pretty(&id).expect("identity serializes");
            std::fs::write(path, text)
                .map_err(|e| format!("writing demo identity {path}: {e}"))?;
            eprintln!("generated fresh demo identity at {path} (gitignored; do not commit)");
            Ok(kp)
        }
        Err(e) => Err(format!("reading identity {path}: {e}")),
    }
}

fn canonical_event_bytes(event: &ActionEvent) -> Vec<u8> {
    serde_json::to_vec(event).expect("event re-serializes")
}

/// Seal one event into a signed record chained onto `prev_record_hash`.
fn seal(
    event: &ActionEvent,
    prev_record_hash: &str,
    keypair: &DilithiumKeyPair,
) -> Result<SealedLine, String> {
    let event_hash = hex::encode(sha3_256(&canonical_event_bytes(event)));
    let binding = ContentBinding {
        event_hash: event_hash.clone(),
        prev_record_hash: prev_record_hash.to_string(),
    };
    let content = serde_json::to_vec(&binding).expect("binding serializes");

    let mut metadata: BTreeMap<String, serde_json::Value> = BTreeMap::new();
    metadata.insert("gbx_agent".into(), serde_json::json!(event.agent));
    metadata.insert("gbx_action".into(), serde_json::json!(event.action));
    metadata.insert("gbx_params".into(), event.params.clone());
    metadata.insert("gbx_ts".into(), serde_json::json!(event.ts));
    metadata.insert("gbx_event_hash".into(), serde_json::json!(event_hash));
    metadata.insert(
        "gbx_prev_record_hash".into(),
        serde_json::json!(prev_record_hash),
    );

    let mut record = ValidationRecord::create(
        &content,
        kp_public(keypair),
        Vec::new(),
        Classification::Public,
        Some(metadata),
    );
    let sig = keypair
        .sign(&record.signable_bytes(), b"")
        .map_err(|e| format!("signing failed: {e:?}"))?;
    record.signature = Some(sig.as_bytes().to_vec());

    Ok(SealedLine {
        record_hash: hex::encode(record.record_hash()),
        record,
    })
}

fn kp_public(kp: &DilithiumKeyPair) -> Vec<u8> {
    kp.public_key().to_vec()
}

/// Re-verify one sealed line in isolation. Returns the record's own hash for
/// chain continuity checking.
fn verify_line(line: &SealedLine, index: usize) -> Result<String, String> {
    let rec = &line.record;
    let recomputed = hex::encode(rec.record_hash());
    if recomputed != line.record_hash {
        return Err(format!(
            "record {index} ({}): stored record_hash does not match recomputed hash",
            rec.id
        ));
    }
    let sig = rec
        .signature
        .as_ref()
        .ok_or_else(|| format!("record {index} ({}): unsigned", rec.id))?;
    let ok = dilithium3_verify(&rec.signable_bytes(), sig, &rec.creator_public_key)
        .map_err(|e| format!("record {index} ({}): verify error: {e}", rec.id))?;
    if !ok {
        return Err(format!(
            "record {index} ({}): ML-DSA-65 signature verification FAILED (content tampered or wrong key)",
            rec.id
        ));
    }
    // Content ↔ metadata binding: the content bytes commit to exactly the
    // (event_hash, prev) pair the metadata displays.
    let event_hash = metadata_str(rec, "gbx_event_hash", index)?;
    let prev = metadata_str(rec, "gbx_prev_record_hash", index)?;
    let binding = ContentBinding {
        event_hash,
        prev_record_hash: prev,
    };
    let expected_content_hash = sha3_256(&serde_json::to_vec(&binding).expect("binding serializes"));
    if expected_content_hash.to_vec() != rec.content_hash {
        return Err(format!(
            "record {index} ({}): content_hash does not bind the metadata's event/prev pair",
            rec.id
        ));
    }
    Ok(recomputed)
}

fn metadata_str(rec: &ValidationRecord, key: &str, index: usize) -> Result<String, String> {
    rec.metadata
        .get(key)
        .and_then(|v| v.as_str())
        .map(str::to_string)
        .ok_or_else(|| format!("record {index} ({}): missing metadata {key}", rec.id))
}

/// Verify a whole chain file (JSON Lines of sealed outputs).
fn verify_chain(text: &str) -> Result<usize, String> {
    let mut expected_prev = GENESIS_PREV.to_string();
    let mut count = 0usize;
    for (i, raw) in text.lines().enumerate() {
        let raw = raw.trim();
        if raw.is_empty() {
            continue;
        }
        let line: SealedLine = serde_json::from_str(raw)
            .map_err(|e| format!("record {i}: unparseable line: {e}"))?;
        let own_hash = verify_line(&line, i)?;
        let prev = metadata_str(&line.record, "gbx_prev_record_hash", i)?;
        if prev != expected_prev {
            return Err(format!(
                "record {i} ({}): CHAIN BREAK — prev_record_hash {} but the previous record's hash is {}",
                line.record.id, prev, expected_prev
            ));
        }
        expected_prev = own_hash;
        count += 1;
    }
    if count == 0 {
        return Err("chain file contains no records".to_string());
    }
    Ok(count)
}

fn validate_prev_hex(s: &str) -> Result<String, String> {
    let p = s.to_lowercase();
    if p.len() != 64 || !p.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("--prev must be 64 hex chars (a record hash)".to_string());
    }
    Ok(p)
}

/// Chain continuation without caller-held state: read the LAST sealed line of
/// an existing chain file and use its record_hash as prev. A missing or empty
/// file starts a fresh chain (genesis prev); a present-but-unparseable tail
/// line is an error (fail loud, never silently fork the chain).
fn prev_from_file(path: &str) -> Result<String, String> {
    let text = match std::fs::read_to_string(path) {
        Ok(t) => t,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            return Ok(GENESIS_PREV.to_string())
        }
        Err(e) => return Err(format!("reading chain file {path}: {e}")),
    };
    match text.lines().rev().find(|l| !l.trim().is_empty()) {
        None => Ok(GENESIS_PREV.to_string()),
        Some(last) => {
            let line: SealedLine = serde_json::from_str(last.trim()).map_err(|e| {
                format!("chain file {path}: last line is not a sealed record ({e}) — refusing to guess prev")
            })?;
            validate_prev_hex(&line.record_hash)
        }
    }
}

fn run() -> Result<(), String> {
    // Stamp the demo network binding once, before any record is created.
    elara_record::record::set_emission_network_id(DEMO_NETWORK_ID)
        .map_err(|e| format!("network binding: {e}"))?;

    let args: Vec<String> = std::env::args().collect();
    if args.len() == 3 && args[1] == "--verify-chain" {
        let text = std::fs::read_to_string(&args[2])
            .map_err(|e| format!("reading chain file {}: {e}", args[2]))?;
        let n = verify_chain(&text)?;
        println!("OK: {n} record(s), every signature valid, every link intact");
        return Ok(());
    }

    // prev precedence: explicit --prev > --prev-from FILE > SEALER_PREV_FROM
    // env (the fleet wrapper points this at its append-only records.jsonl so
    // consecutive actions chain without the caller tracking state) > genesis.
    let prev = match args.len() {
        1 => match std::env::var("SEALER_PREV_FROM") {
            Ok(path) => prev_from_file(&path)?,
            Err(_) => GENESIS_PREV.to_string(),
        },
        3 if args[1] == "--prev" => validate_prev_hex(&args[2])?,
        3 if args[1] == "--prev-from" => prev_from_file(&args[2])?,
        _ => {
            return Err(
                "usage: sealer [--prev <64-hex> | --prev-from <chain.jsonl>] < event.json\n       sealer --verify-chain <chain.jsonl>"
                    .to_string(),
            )
        }
    };

    let mut input = String::new();
    std::io::stdin()
        .read_to_string(&mut input)
        .map_err(|e| format!("reading stdin: {e}"))?;
    let event: ActionEvent = serde_json::from_str(&input)
        .map_err(|e| format!("stdin is not a valid action-event: {e}"))?;

    let identity_path =
        std::env::var("SEALER_IDENTITY").unwrap_or_else(|_| "sealer-identity.json".to_string());
    let keypair = load_or_generate_identity(&identity_path)?;

    let sealed = seal(&event, &prev, &keypair)?;
    println!(
        "{}",
        serde_json::to_string(&sealed).expect("sealed line serializes")
    );
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("{e}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn demo_event(action: &str) -> ActionEvent {
        ActionEvent {
            agent: "buyer-1".into(),
            action: action.into(),
            params: serde_json::json!({"sku": "WIDGET-9", "qty": 3}),
            ts: serde_json::json!(1_756_000_000.0),
        }
    }

    #[test]
    fn iso_string_ts_event_seals_and_verifies() {
        // The fleet wrapper emits ts as an ISO-8601 STRING — the sealer must
        // treat ts as opaque evidence content, not parse it.
        let kp = demo_keypair();
        let event: ActionEvent = serde_json::from_str(
            r#"{"agent":"buyer-1","action":"create_po","params":{"sku":"W"},"ts":"2026-08-27T06:30:00Z"}"#,
        )
        .expect("string-ts event parses");
        let sealed = seal(&event, GENESIS_PREV, &kp).expect("seal");
        verify_line(&sealed, 0).expect("line verifies");
    }

    #[test]
    fn prev_from_file_reads_last_hash_and_handles_fresh_start() {
        let kp = demo_keypair();
        let dir = std::env::temp_dir().join(format!("gbx-prevfrom-{}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("mkdir");
        let path = dir.join("records.jsonl");
        let path_str = path.to_str().expect("utf8 path");
        // Missing file → genesis.
        assert_eq!(prev_from_file(path_str).expect("fresh"), GENESIS_PREV);
        // Two sealed lines → last line's hash.
        let a = seal(&demo_event("create_po"), GENESIS_PREV, &kp).expect("seal a");
        let b = seal(&demo_event("approve_po"), &a.record_hash, &kp).expect("seal b");
        let text = format!(
            "{}\n{}\n",
            serde_json::to_string(&a).unwrap(),
            serde_json::to_string(&b).unwrap()
        );
        std::fs::write(&path, text).expect("write chain");
        assert_eq!(prev_from_file(path_str).expect("tail"), b.record_hash);
        // Garbage tail → loud error, never a silent fork.
        std::fs::write(&path, "not json\n").expect("write garbage");
        assert!(prev_from_file(path_str).is_err(), "garbage tail must error");
        std::fs::remove_dir_all(&dir).ok();
    }

    fn demo_keypair() -> DilithiumKeyPair {
        DilithiumKeyPair::generate(MODE).expect("keygen")
    }

    #[test]
    fn seal_then_verify_roundtrip_via_elara_record_verify_fn() {
        let kp = demo_keypair();
        let sealed = seal(&demo_event("create_po"), GENESIS_PREV, &kp).expect("seal");
        // The record verifies with elara-record's OWN verify function over its
        // own signed preimage — the exact check any third-party verifier of
        // the published format runs.
        let ok = dilithium3_verify(
            &sealed.record.signable_bytes(),
            sealed.record.signature.as_ref().expect("signed"),
            &sealed.record.creator_public_key,
        )
        .expect("verify runs");
        assert!(ok, "sealed record must verify with elara_record::pqc::dilithium3_verify");
        // And the full line-level check (hash + binding) passes.
        verify_line(&sealed, 0).expect("line verifies");
    }

    #[test]
    fn one_byte_tamper_is_detected() {
        let kp = demo_keypair();
        let mut sealed = seal(&demo_event("create_po"), GENESIS_PREV, &kp).expect("seal");
        // Tamper with the signed surface: change the action the metadata
        // claims. The signature must stop verifying.
        sealed
            .record
            .metadata
            .insert("gbx_action".into(), serde_json::json!("create_p0"));
        let ok = dilithium3_verify(
            &sealed.record.signable_bytes(),
            sealed.record.signature.as_ref().expect("signed"),
            &sealed.record.creator_public_key,
        )
        .expect("verify runs");
        assert!(!ok, "a one-byte metadata tamper must break the signature");
    }

    #[test]
    fn chain_verifies_and_link_break_is_detected() {
        let kp = demo_keypair();
        let a = seal(&demo_event("create_po"), GENESIS_PREV, &kp).expect("seal a");
        let b = seal(&demo_event("approve_po"), &a.record_hash, &kp).expect("seal b");
        let c = seal(&demo_event("pay_invoice"), &b.record_hash, &kp).expect("seal c");
        let good = [&a, &b, &c]
            .iter()
            .map(|l| serde_json::to_string(l).unwrap())
            .collect::<Vec<_>>()
            .join("\n");
        assert_eq!(verify_chain(&good).expect("good chain verifies"), 3);

        // Drop the middle record: c's prev no longer matches a's hash.
        let broken = [&a, &c]
            .iter()
            .map(|l| serde_json::to_string(l).unwrap())
            .collect::<Vec<_>>()
            .join("\n");
        let err = verify_chain(&broken).expect_err("gap must be detected");
        assert!(err.contains("CHAIN BREAK"), "got: {err}");

        // Splice attack, lazy variant: rewrite b's prev pointer without
        // re-signing or fixing the stored hash — dies at the hash-integrity
        // check (record_hash covers metadata).
        let mut spliced_b = seal(&demo_event("approve_po"), &a.record_hash, &kp).expect("seal");
        spliced_b
            .record
            .metadata
            .insert("gbx_prev_record_hash".into(), serde_json::json!(GENESIS_PREV));
        let spliced = [&a, &spliced_b]
            .iter()
            .map(|l| serde_json::to_string(l).unwrap())
            .collect::<Vec<_>>()
            .join("\n");
        let err = verify_chain(&spliced).expect_err("lazy splice must be detected");
        assert!(
            err.contains("does not match recomputed hash"),
            "lazy splice must die at the hash-integrity check, got: {err}"
        );

        // Splice attack, diligent variant: the attacker ALSO recomputes and
        // fixes the stored record_hash after mutating the prev pointer — the
        // hash check now passes, so the ML-DSA-65 signature is what must
        // refuse (nothing rewrites history without the signing key).
        spliced_b.record_hash = hex::encode(spliced_b.record.record_hash());
        let spliced2 = [&a, &spliced_b]
            .iter()
            .map(|l| serde_json::to_string(l).unwrap())
            .collect::<Vec<_>>()
            .join("\n");
        let err = verify_chain(&spliced2).expect_err("diligent splice must be detected");
        assert!(
            err.contains("signature verification FAILED"),
            "diligent splice must die at the signature, got: {err}"
        );
    }

    #[test]
    fn identity_file_roundtrip_loads_same_key() {
        let dir = std::env::temp_dir().join(format!("gbx-sealer-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("mkdir");
        let path = dir.join("identity.json");
        let path_str = path.to_str().expect("utf8 path");
        let kp1 = load_or_generate_identity(path_str).expect("generate");
        let kp2 = load_or_generate_identity(path_str).expect("reload");
        assert_eq!(kp1.public_key(), kp2.public_key(), "reload must yield the same identity");
        std::fs::remove_dir_all(&dir).ok();
    }
}

//! Mahsa sidecar entrypoint. Loads the rule set (from `MAHSA_RULES` file if set, else the
//! embedded default) and serves on `MAHSA_ADDR` (default `0.0.0.0:8088`).

use mahsa::app::build_router;
use mahsa::validate::RuleSet;

#[tokio::main]
async fn main() {
    let rules = match std::env::var("MAHSA_RULES") {
        Ok(path) => {
            // WS1.E3: a file-loaded pack must arrive WITH its manifest and pass sha256 +
            // version verification — fail loud at boot, never serve an unverified pack.
            let manifest_path = std::env::var("MAHSA_RULES_MANIFEST").unwrap_or_else(|_| {
                panic!(
                    "MAHSA_RULES is set but MAHSA_RULES_MANIFEST is not: a rule pack loads \
                     only with its manifest (version + sha256), see docs/RULE_PACK_SLA.md"
                )
            });
            let text = std::fs::read_to_string(&path)
                .unwrap_or_else(|e| panic!("cannot read MAHSA_RULES={path}: {e}"));
            let manifest = std::fs::read_to_string(&manifest_path).unwrap_or_else(|e| {
                panic!("cannot read MAHSA_RULES_MANIFEST={manifest_path}: {e}")
            });
            RuleSet::load_verified(&text, &manifest)
                .unwrap_or_else(|e| panic!("rule pack failed manifest verification: {e}"))
        }
        Err(_) => RuleSet::embedded(),
    };

    let addr = std::env::var("MAHSA_ADDR").unwrap_or_else(|_| "0.0.0.0:8088".to_string());
    let app = build_router(rules);

    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .unwrap_or_else(|e| panic!("cannot bind {addr}: {e}"));
    println!(
        "Mahsa v{} listening on http://{addr}  (GET /health, POST /fold)",
        mahsa::ENGINE_VERSION
    );
    axum::serve(listener, app).await.expect("server error");
}

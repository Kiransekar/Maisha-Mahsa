//! Mahsa sidecar entrypoint. Loads the rule set (from `MAHSA_RULES` file if set, else the
//! embedded default) and serves on `MAHSA_ADDR` (default `0.0.0.0:8088`).

use mahsa::app::build_router;
use mahsa::validate::RuleSet;

#[tokio::main]
async fn main() {
    let rules = match std::env::var("MAHSA_RULES") {
        Ok(path) => {
            let text = std::fs::read_to_string(&path)
                .unwrap_or_else(|e| panic!("cannot read MAHSA_RULES={path}: {e}"));
            RuleSet::from_yaml(&text).expect("rules.yaml failed validation")
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

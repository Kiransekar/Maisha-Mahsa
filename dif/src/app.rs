//! The HTTP surface: `GET /health` and `POST /fold`. The router is built from a `RuleSet`
//! so tests can construct it in-process (see `tests/integration.rs`).

use crate::fold::fold;
use crate::intent::{IntentVec, GLOBAL_DIMS};
use crate::snapshot::{Domain, FoldRequest};
use crate::unfold::{unfold, ResponseShape};
use crate::validate::{validate, RuleSet, Validation};
use axum::{
    extract::{DefaultBodyLimit, State},
    routing::{get, post},
    Json, Router,
};
use serde::Serialize;
use std::sync::Arc;
use tower_http::catch_panic::CatchPanicLayer;

#[derive(Clone)]
pub struct AppState {
    pub rules: Arc<RuleSet>,
}

#[derive(Serialize)]
pub struct Health {
    pub status: &'static str,
    pub engine_version: &'static str,
    pub rules_version: String,
}

#[derive(Serialize)]
pub struct FoldResponse {
    pub global_intent: IntentVec,
    pub global_dims: [&'static str; 8],
    pub domain: Option<String>,
    pub domain_intent: Option<IntentVec>,
    pub validation: Validation,
    pub shape: ResponseShape,
    pub rules_version: String,
}

pub fn build_router(rules: RuleSet) -> Router {
    let state = AppState {
        rules: Arc::new(rules),
    };
    Router::new()
        .route("/health", get(health))
        .route("/fold", post(fold_handler))
        // Any handler panic becomes a 500 instead of resetting the connection; cap the request body.
        .layer(CatchPanicLayer::new())
        .layer(DefaultBodyLimit::max(256 * 1024))
        .with_state(state)
}

async fn health(State(st): State<AppState>) -> Json<Health> {
    Json(Health {
        status: "ok",
        engine_version: crate::ENGINE_VERSION,
        rules_version: st.rules.version.clone(),
    })
}

async fn fold_handler(
    State(st): State<AppState>,
    Json(req): Json<FoldRequest>,
) -> Json<FoldResponse> {
    let domain = req.domain.as_deref().and_then(Domain::parse);
    let f = fold(&req.snapshot, domain);
    let v = validate(&f.global, &req.snapshot, domain, &st.rules);
    let shape = unfold(&f, &v);
    Json(FoldResponse {
        global_intent: f.global,
        global_dims: GLOBAL_DIMS,
        domain: f.domain.as_ref().map(|(d, _)| d.as_str().to_string()),
        domain_intent: f.domain.as_ref().map(|(_, iv)| *iv),
        validation: v,
        shape,
        rules_version: st.rules.version.clone(),
    })
}

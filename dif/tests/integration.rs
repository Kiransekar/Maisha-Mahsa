//! HTTP integration tests against the real axum router (no network; uses tower oneshot).

use axum::body::{to_bytes, Body};
use axum::http::{Request, StatusCode};
use mahsa::app::build_router;
use mahsa::validate::RuleSet;
use serde_json::{json, Value};
use tower::ServiceExt; // for `oneshot`

async fn post_fold(body: Value) -> (StatusCode, Value) {
    let app = build_router(RuleSet::embedded());
    let resp = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/fold")
                .header("content-type", "application/json")
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    let status = resp.status();
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: Value = serde_json::from_slice(&bytes).unwrap();
    (status, v)
}

#[tokio::test]
async fn health_reports_versions() {
    let app = build_router(RuleSet::embedded());
    let resp = app
        .oneshot(
            Request::builder()
                .uri("/health")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(v["status"], "ok");
    assert!(v["rules_version"].is_string());
}

#[tokio::test]
async fn fold_short_runway_is_red_with_citation() {
    let (status, v) = post_fold(json!({
        "domain": "treasury",
        "snapshot": { "cash": 10000000, "monthly_burn": 10000000, "monthly_revenue": 0 }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["validation"]["status"], "red");
    assert_eq!(v["shape"]["requires_approval"], true);
    assert_eq!(v["domain"], "treasury");
    // global intent has 8 dims; domain sub-vector present for treasury
    assert_eq!(v["global_intent"].as_array().unwrap().len(), 8);
    assert_eq!(v["domain_intent"].as_array().unwrap().len(), 8);
    let banners = v["shape"]["banners"].as_array().unwrap();
    assert!(banners
        .iter()
        .any(|b| b["citation"].as_str().unwrap().contains("—")));
}

#[tokio::test]
async fn fold_healthy_is_green_no_approval() {
    let (status, v) = post_fold(json!({
        "domain": "treasury",
        "snapshot": { "cash": 120000000, "monthly_burn": 5000000, "monthly_revenue": 6000000 }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["validation"]["status"], "green");
    assert_eq!(v["shape"]["requires_approval"], false);
}

#[tokio::test]
async fn fold_payroll_negative_net_pay_is_red() {
    let (status, v) = post_fold(json!({
        "domain": "payroll",
        "snapshot": {
            "cash": 50000000, "monthly_burn": 2000000, "monthly_revenue": 3000000,
            "metrics": { "min_net_pay_paise": -100, "pf_compliance": 1.0 }
        }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["domain"], "payroll");
    assert_eq!(v["domain_intent"].as_array().unwrap().len(), 8);
    assert_eq!(v["validation"]["status"], "red");
    assert!(v["validation"]["triggered"]
        .as_array()
        .unwrap()
        .iter()
        .any(|t| t["id"] == "PAYROLL-003"));
}

#[tokio::test]
async fn fold_gst_late_filing_is_red() {
    let (status, v) = post_fold(json!({
        "domain": "gst",
        "snapshot": {
            "cash": 50000000, "monthly_burn": 2000000, "monthly_revenue": 3000000,
            "metrics": { "gstr3b_days_late": 4, "filing_timeliness": 0.0 }
        }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["domain"], "gst");
    assert_eq!(v["domain_intent"].as_array().unwrap().len(), 8);
    assert_eq!(v["validation"]["status"], "red"); // GST-001 is a block
    assert!(v["validation"]["triggered"]
        .as_array()
        .unwrap()
        .iter()
        .any(|t| t["id"] == "GST-001"));
}

#[tokio::test]
async fn fold_revenue_missing_einvoice_above_threshold_is_red() {
    // turnover > ₹5Cr and an invoice without IRN -> REVENUE-001 block.
    let (status, v) = post_fold(json!({
        "domain": "revenue",
        "snapshot": {
            "cash": 50000000, "monthly_burn": 2000000, "monthly_revenue": 3000000,
            "metrics": { "annual_turnover_rupees": 60000000, "einvoice_missing": 2, "irn_coverage": 0.0 }
        }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["domain"], "revenue");
    assert_eq!(v["domain_intent"].as_array().unwrap().len(), 8);
    assert_eq!(v["validation"]["status"], "red");
    assert!(v["validation"]["triggered"]
        .as_array()
        .unwrap()
        .iter()
        .any(|t| t["id"] == "REVENUE-001"));
}

#[tokio::test]
async fn fold_payables_msme_overdue_is_yellow() {
    // MSME vendor unpaid 60 days -> PAYABLES-001 warning -> Yellow.
    let (status, v) = post_fold(json!({
        "domain": "payables",
        "snapshot": {
            "cash": 50000000, "monthly_burn": 2000000, "monthly_revenue": 3000000,
            "metrics": { "msme_max_days_unpaid": 60, "msme_compliance": 0.0 }
        }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["domain"], "payables");
    assert_eq!(v["domain_intent"].as_array().unwrap().len(), 8);
    assert_eq!(v["validation"]["status"], "yellow");
    assert!(v["validation"]["triggered"]
        .as_array()
        .unwrap()
        .iter()
        .any(|t| t["id"] == "PAYABLES-001"));
}

#[tokio::test]
async fn fold_tax_late_tds_deposit_is_red() {
    // TDS not deposited by the 7th -> TAX-002 block -> Red.
    let (status, v) = post_fold(json!({
        "domain": "tax",
        "snapshot": {
            "cash": 50000000, "monthly_burn": 2000000, "monthly_revenue": 3000000,
            "metrics": { "tds_days_overdue": 5, "tds_deposit_timeliness": 0.0 }
        }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["domain"], "tax");
    assert_eq!(v["domain_intent"].as_array().unwrap().len(), 8);
    assert_eq!(v["validation"]["status"], "red");
    assert!(v["validation"]["triggered"]
        .as_array()
        .unwrap()
        .iter()
        .any(|t| t["id"] == "TAX-002"));
}

#[tokio::test]
async fn fold_ledger_unbalanced_trial_balance_is_red() {
    // ledger has no sub-vector, but a domain-scoped rule still fires: LEDGER-001.
    let (status, v) = post_fold(json!({
        "domain": "ledger",
        "snapshot": {
            "cash": 50000000, "monthly_burn": 2000000, "monthly_revenue": 3000000,
            "metrics": { "trial_balance_diff_paise": 100 }
        }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["domain"], serde_json::Value::Null); // no sub-vector fold for ledger
    assert!(v["domain_intent"].is_null());
    assert_eq!(v["validation"]["status"], "red");
    assert!(v["validation"]["triggered"]
        .as_array()
        .unwrap()
        .iter()
        .any(|t| t["id"] == "LEDGER-001"));
}

#[tokio::test]
async fn fold_compliance_overdue_filing_is_yellow() {
    // An overdue statutory filing -> COMPLIANCE-002 (global warning) -> Yellow, with the
    // compliance sub-vector present.
    let (status, v) = post_fold(json!({
        "domain": "compliance",
        "snapshot": {
            "cash": 50000000, "monthly_burn": 2000000, "monthly_revenue": 3000000,
            "overdue_filings": 2,
            "metrics": { "gst_filing_status": 0.0 }
        }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["domain"], "compliance");
    assert_eq!(v["domain_intent"].as_array().unwrap().len(), 8);
    assert_eq!(v["validation"]["status"], "yellow");
    assert!(v["validation"]["triggered"]
        .as_array()
        .unwrap()
        .iter()
        .any(|t| t["id"] == "COMPLIANCE-002"));
}

#[tokio::test]
async fn fold_equity_esop_over_cap_without_approval_is_red() {
    // ESOP pool 12% with no board approval -> EQUITY-001 block -> Red.
    let (status, v) = post_fold(json!({
        "domain": "equity",
        "snapshot": {
            "cash": 50000000, "monthly_burn": 2000000, "monthly_revenue": 3000000,
            "metrics": { "esop_pool_pct": 0.12, "esop_board_approved": 0, "esop_utilization": 0.5 }
        }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["domain"], "equity");
    assert_eq!(v["domain_intent"].as_array().unwrap().len(), 8);
    assert_eq!(v["validation"]["status"], "red");
    assert!(v["validation"]["triggered"]
        .as_array()
        .unwrap()
        .iter()
        .any(|t| t["id"] == "EQUITY-001"));
}

#[tokio::test]
async fn fold_forecast_projected_overdraft_is_yellow() {
    // forecast has no sub-vector, but FORECAST-001 (domain-scoped) fires on a projected shortfall.
    let (status, v) = post_fold(json!({
        "domain": "forecast",
        "snapshot": {
            "cash": 50000000, "monthly_burn": 2000000, "monthly_revenue": 3000000,
            "metrics": { "forecast_min_cash_paise": -100 }
        }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["domain"], serde_json::Value::Null); // no sub-vector fold for forecast
    assert!(v["domain_intent"].is_null());
    assert_eq!(v["validation"]["status"], "yellow");
    assert!(v["validation"]["triggered"]
        .as_array()
        .unwrap()
        .iter()
        .any(|t| t["id"] == "FORECAST-001"));
}

#[tokio::test]
async fn fold_expense_over_policy_is_yellow() {
    // expense has no sub-vector; EXPENSE-001 (domain-scoped) fires on an over-policy claim.
    let (status, v) = post_fold(json!({
        "domain": "expense",
        "snapshot": {
            "cash": 50000000, "monthly_burn": 2000000, "monthly_revenue": 3000000,
            "metrics": { "over_policy_claims": 1 }
        }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["domain"], serde_json::Value::Null); // no sub-vector fold for expense
    assert!(v["domain_intent"].is_null());
    assert_eq!(v["validation"]["status"], "yellow");
    assert!(v["validation"]["triggered"]
        .as_array()
        .unwrap()
        .iter()
        .any(|t| t["id"] == "EXPENSE-001"));
}

#[tokio::test]
async fn fold_vault_integrity_failure_is_red() {
    // vault has no sub-vector; VAULT-001 (domain-scoped) blocks on a hash-integrity failure.
    let (status, v) = post_fold(json!({
        "domain": "vault",
        "snapshot": {
            "cash": 50000000, "monthly_burn": 2000000, "monthly_revenue": 3000000,
            "metrics": { "integrity_failures": 1 }
        }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(v["domain"], serde_json::Value::Null); // no sub-vector fold for vault
    assert!(v["domain_intent"].is_null());
    assert_eq!(v["validation"]["status"], "red");
    assert!(v["validation"]["triggered"]
        .as_array()
        .unwrap()
        .iter()
        .any(|t| t["id"] == "VAULT-001"));
}

#[tokio::test]
async fn fold_without_domain_runs_global_only() {
    let (status, v) = post_fold(json!({
        "snapshot": { "cash": 50000000, "monthly_burn": 2000000, "monthly_revenue": 3000000 }
    }))
    .await;
    assert_eq!(status, StatusCode::OK);
    assert!(v["domain"].is_null());
    assert!(v["domain_intent"].is_null());
    assert_eq!(v["shape"]["layout"], "global");
}

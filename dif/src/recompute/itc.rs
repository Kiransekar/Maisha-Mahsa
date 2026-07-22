//! GST input-tax-credit set-off, CGST Act s.49(5)/49A/49B r/w Rule 88A (mirror of
//! app/domains/gst/gst_calc.py::itc_setoff — the two MUST stay paisa-identical).
//! Heads are ordered [igst, cgst, sgst]. §WS3.1.
//!
//! Rule 88A r/w Circular No. 98/17/2019-GST: IGST credit → IGST liability first, then the
//! remainder → CGST/SGST "in any order and in any proportion", "completely exhausted
//! mandatorily" before CGST/SGST credit is used. We choose the CASH-MINIMIZING split:
//! uncovered needs (liability minus own credit) first, CGST before SGST on the tie-break
//! (total cash is invariant to it), then mandatory exhaustion CGST-first. CGST and SGST
//! credit never cross (s.49(5)(c)/(d) provisos). Interpretation choice recorded in
//! api/tests/statutory_oracle/vectors/ws1d_itc_setoff.yaml (ca_initials: OWNER).

/// Apply ITC against output tax; returns (cash_payable_per_head, remaining_credit_per_head),
/// heads in order [igst, cgst, sgst]. All paise.
pub fn itc_setoff(output: [i64; 3], credit: [i64; 3]) -> ([i64; 3], [i64; 3]) {
    const IGST: usize = 0;
    const CGST: usize = 1;
    const SGST: usize = 2;

    let mut out = output;
    let mut cr = credit;

    fn apply(src: usize, dst: usize, cap: Option<i64>, out: &mut [i64; 3], cr: &mut [i64; 3]) {
        let mut amt = cr[src].min(out[dst]);
        if let Some(c) = cap {
            amt = amt.min(c);
        }
        cr[src] -= amt;
        out[dst] -= amt;
    }

    apply(IGST, IGST, None, &mut out, &mut cr);
    // Rule 88A cash-minimizing allocation: uncovered needs first, then mandatory exhaustion.
    let need_c = (out[CGST] - cr[CGST]).max(0);
    apply(IGST, CGST, Some(need_c), &mut out, &mut cr);
    let need_s = (out[SGST] - cr[SGST]).max(0);
    apply(IGST, SGST, Some(need_s), &mut out, &mut cr);
    apply(IGST, CGST, None, &mut out, &mut cr);
    apply(IGST, SGST, None, &mut out, &mut cr);
    apply(CGST, CGST, None, &mut out, &mut cr);
    apply(CGST, IGST, None, &mut out, &mut cr);
    apply(SGST, SGST, None, &mut out, &mut cr);
    apply(SGST, IGST, None, &mut out, &mut cr);

    (out, cr)
}

#[cfg(test)]
mod tests {
    use super::itc_setoff;

    fn rupees(r: i64) -> i64 {
        r * 100
    }

    #[test]
    fn igst_credit_cash_minimizing_allocation() {
        // Mirrors test_itc_setoff_igst_credit_cash_minimizing: IGST ₹150 covers the uncovered
        // needs (₹80 CGST, then ₹70 of the ₹80 SGST need); own credits ₹20+₹20 fill the rest,
        // leaving ₹10 SGST cash. The old fixed IGST→CGST-first order stranded the ₹20 CGST
        // credit and paid ₹30 cash.
        let out = [rupees(0), rupees(100), rupees(100)]; // igst, cgst, sgst
        let cr = [rupees(150), rupees(20), rupees(20)];
        let (cash, remaining_credit) = itc_setoff(out, cr);
        assert_eq!(cash, [rupees(0), rupees(0), rupees(10)]);
        assert_eq!(remaining_credit, [0, 0, 0]); // every rupee of credit utilised
    }

    #[test]
    fn igst_allocation_boundary_paired() {
        // PAIRED boundary: IGST credit exactly covers both uncovered needs -> zero cash...
        // needs: cgst 10000-2000=8000, sgst 10000-3000=7000; igst credit = 15000 exactly.
        let out = [0, 10000, 10000];
        let (cash, rem) = itc_setoff(out, [15000, 2000, 3000]);
        assert_eq!(cash, [0, 0, 0]);
        assert_eq!(rem, [0, 0, 0]);
        // ...and one paisa short -> exactly one paisa of cash (on SGST, the tie-break tail).
        let (cash, rem) = itc_setoff(out, [14999, 2000, 3000]);
        assert_eq!(cash, [0, 0, 1]);
        assert_eq!(rem, [0, 0, 0]);
    }

    #[test]
    fn mandatory_exhaustion_displaces_own_credit() {
        // Rule 88A proviso: IGST credit is exhausted even where own credit could have covered
        // the head — the displaced CGST credit carries forward, cash unchanged (nil).
        let (cash, rem) = itc_setoff([0, 5000, 5000], [12000, 4000, 0]);
        assert_eq!(cash, [0, 0, 0]);
        assert_eq!(rem, [2000, 4000, 0]); // igst leftover + displaced cgst credit
    }

    #[test]
    fn cgst_cannot_offset_sgst() {
        // Mirrors test_itc_cgst_cannot_offset_sgst: CGST credit may not touch SGST output ->
        // SGST must be paid in cash, CGST credit sits unused.
        let out = [rupees(0), rupees(0), rupees(100)];
        let cr = [rupees(0), rupees(100), rupees(0)];
        let (cash, remaining_credit) = itc_setoff(out, cr);
        assert_eq!(cash[2], rupees(100));
        assert_eq!(remaining_credit[1], rupees(100));
    }

    #[test]
    fn sgst_cannot_offset_cgst() {
        // Symmetric case (not in Python suite but proves the mirror-image rule holds):
        // SGST credit may not touch CGST output.
        let out = [rupees(0), rupees(100), rupees(0)];
        let cr = [rupees(0), rupees(0), rupees(100)];
        let (cash, remaining_credit) = itc_setoff(out, cr);
        assert_eq!(cash[1], rupees(100));
        assert_eq!(remaining_credit[2], rupees(100));
    }

    #[test]
    fn all_zero_is_identity() {
        let (cash, remaining_credit) = itc_setoff([0, 0, 0], [0, 0, 0]);
        assert_eq!(cash, [0, 0, 0]);
        assert_eq!(remaining_credit, [0, 0, 0]);
    }
}

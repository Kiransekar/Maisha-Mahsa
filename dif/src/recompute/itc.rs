//! GST input-tax-credit set-off in statutory order, Rule 88A (mirror of
//! app/domains/gst/gst_calc.py::itc_setoff). Heads are ordered [igst, cgst, sgst]. §WS3.1.

/// Apply ITC against output tax; returns (cash_payable_per_head, remaining_credit_per_head),
/// heads in order [igst, cgst, sgst]. All paise.
pub fn itc_setoff(output: [i64; 3], credit: [i64; 3]) -> ([i64; 3], [i64; 3]) {
    const IGST: usize = 0;
    const CGST: usize = 1;
    const SGST: usize = 2;

    let mut out = output;
    let mut cr = credit;

    fn apply(src: usize, dst: usize, out: &mut [i64; 3], cr: &mut [i64; 3]) {
        let amt = cr[src].min(out[dst]);
        cr[src] -= amt;
        out[dst] -= amt;
    }

    apply(IGST, IGST, &mut out, &mut cr);
    apply(IGST, CGST, &mut out, &mut cr);
    apply(IGST, SGST, &mut out, &mut cr);
    apply(CGST, CGST, &mut out, &mut cr);
    apply(CGST, IGST, &mut out, &mut cr);
    apply(SGST, SGST, &mut out, &mut cr);
    apply(SGST, IGST, &mut out, &mut cr);

    (out, cr)
}

#[cfg(test)]
mod tests {
    use super::itc_setoff;

    fn rupees(r: i64) -> i64 {
        r * 100
    }

    #[test]
    fn igst_credit_cascades() {
        // Mirrors test_itc_setoff_igst_credit_cascades: IGST credit ₹150 covers ₹100 CGST
        // then ₹50 SGST; SGST credit ₹20 clears part of the remaining ₹50 SGST, leaving ₹30 cash.
        let out = [rupees(0), rupees(100), rupees(100)]; // igst, cgst, sgst
        let cr = [rupees(150), rupees(20), rupees(20)];
        let (cash, remaining_credit) = itc_setoff(out, cr);
        assert_eq!(cash, [rupees(0), rupees(0), rupees(30)]);
        assert_eq!(remaining_credit[1], rupees(20)); // cgst credit untouched
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

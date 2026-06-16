from app.core.domain import FeatureState
from app.domains.treasury.manifest import MANIFEST


def test_treasury_manifest_tracks_features():
    keys = {f.key for f in MANIFEST.features}
    assert {"cash_position", "burn", "runway", "multi_bank_csv"} <= keys


def test_pct_done_reflects_done_features():
    done = sum(1 for f in MANIFEST.features if f.state is FeatureState.DONE)
    assert MANIFEST.pct_done() == round(100.0 * done / len(MANIFEST.features), 1)
    assert not MANIFEST.is_complete  # treasury still has pending features

from pathlib import Path
from types import SimpleNamespace

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures():
    return FIXTURES


@pytest.fixture
def opts():
    """Options object as produced by the CLI parser or the app's make_opts()."""
    def make(**kw):
        base = dict(quality=90, dpi=150, extract_images=False, ocr_lang=None, force=False)
        base.update(kw)
        return SimpleNamespace(**base)
    return make

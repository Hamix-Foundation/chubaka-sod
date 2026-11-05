import numpy as np
import pytest

from lysyk.engine import noise
from tests.reference import noise as ref


@pytest.mark.parametrize("seed", [0, 3, 17, -5])
def test_value_matches_reference(seed):
    rng = np.random.default_rng(seed + 10)
    x = rng.uniform(-500, 500, (37, 21))
    z = rng.uniform(-500, 500, (37, 21))
    np.testing.assert_allclose(noise.value(x, z, seed), ref.value(x, z, seed), atol=1e-12)


def test_fbm_ridged_match_reference():
    rng = np.random.default_rng(1)
    x = rng.uniform(-900, 900, 5000)
    z = rng.uniform(-900, 900, 5000)
    np.testing.assert_allclose(noise.fbm(x, z, 5, 7), ref.fbm(x, z, 5, 7), atol=1e-12)
    np.testing.assert_allclose(noise.ridged(x, z, 3, 2), ref.ridged(x, z, 3, 2), atol=1e-12)


def test_scalar_and_broadcast():
    assert float(noise.value(1.3, 2.7, 4)) == pytest.approx(float(ref.value(1.3, 2.7, 4)))
    x = np.linspace(0, 10, 8)[:, None]
    z = np.linspace(0, 10, 5)[None, :]
    assert noise.fbm(x, z).shape == (8, 5)
    np.testing.assert_allclose(noise.fbm(x, z), ref.fbm(x, z), atol=1e-12)

use numpy::{PyArray1, PyReadonlyArray1};
use pyo3::prelude::*;
use rayon::prelude::*;

const M: u64 = 0xFFFF_FFFF;

#[inline]
fn hash(ix: i64, iz: i64, seed_term: u64) -> f64 {
    let mut h = (ix as u64).wrapping_mul(374761393).wrapping_add((iz as u64).wrapping_mul(668265263)).wrapping_add(seed_term) & M;
    h = ((h ^ (h >> 13)).wrapping_mul(1274126177)) & M;
    h ^= h >> 16;
    (h & 0xFF_FFFF) as f64 / 16777216.0
}

#[inline]
fn seed_term(seed: i64) -> u64 {
    ((seed as i128 * 2246822519i128).rem_euclid(1i128 << 32)) as u64
}

#[inline]
fn value(x: f64, z: f64, st: u64) -> f64 {
    let fx = x.floor();
    let fz = z.floor();
    let (ix, iz) = (fx as i64, fz as i64);
    let mut tx = x - fx;
    let mut tz = z - fz;
    tx = tx * tx * (3.0 - 2.0 * tx);
    tz = tz * tz * (3.0 - 2.0 * tz);
    let a = hash(ix, iz, st);
    let b = hash(ix + 1, iz, st);
    let c = hash(ix, iz + 1, st);
    let d = hash(ix + 1, iz + 1, st);
    (a + (b - a) * tx) * (1.0 - tz) + (c + (d - c) * tx) * tz
}

fn fbm(x: f64, z: f64, octaves: u32, seed: i64, lac: f64, gain: f64) -> f64 {
    let mut total = 0.0;
    let mut amp = 1.0;
    let mut norm = 0.0;
    let mut fx = 1.0;
    for o in 0..octaves {
        total += amp * value(x * fx, z * fx, seed_term(seed + o as i64 * 17));
        norm += amp;
        amp *= gain;
        fx *= lac;
    }
    total / norm
}

fn map2(py: Python<'_>, x: PyReadonlyArray1<'_, f64>, z: PyReadonlyArray1<'_, f64>, f: impl Fn(f64, f64) -> f64 + Sync) -> PyResult<Py<PyArray1<f64>>> {
    let xs = x.as_slice()?;
    let zs = z.as_slice()?;
    if xs.len() != zs.len() {
        return Err(pyo3::exceptions::PyValueError::new_err("x and z must have the same length"));
    }
    let out: Vec<f64> = py.detach(|| {
        if xs.len() > 4096 {
            xs.par_iter().zip(zs.par_iter()).map(|(a, b)| f(*a, *b)).collect()
        } else {
            xs.iter().zip(zs.iter()).map(|(a, b)| f(*a, *b)).collect()
        }
    });
    Ok(PyArray1::from_vec(py, out).unbind())
}

#[pyfunction]
#[pyo3(name = "value_flat", signature = (x, z, seed=0))]
fn value_flat(py: Python<'_>, x: PyReadonlyArray1<'_, f64>, z: PyReadonlyArray1<'_, f64>, seed: i64) -> PyResult<Py<PyArray1<f64>>> {
    let st = seed_term(seed);
    map2(py, x, z, move |a, b| value(a, b, st))
}

#[pyfunction]
#[pyo3(name = "fbm_flat", signature = (x, z, octaves=4, seed=0, lacunarity=2.0, gain=0.5))]
fn fbm_flat(
    py: Python<'_>, x: PyReadonlyArray1<'_, f64>, z: PyReadonlyArray1<'_, f64>, octaves: u32, seed: i64, lacunarity: f64, gain: f64,
) -> PyResult<Py<PyArray1<f64>>> {
    map2(py, x, z, move |a, b| fbm(a, b, octaves, seed, lacunarity, gain))
}

#[pyfunction]
#[pyo3(name = "ridged_flat", signature = (x, z, octaves=4, seed=0))]
fn ridged_flat(py: Python<'_>, x: PyReadonlyArray1<'_, f64>, z: PyReadonlyArray1<'_, f64>, octaves: u32, seed: i64) -> PyResult<Py<PyArray1<f64>>> {
    map2(py, x, z, move |a, b| 1.0 - (2.0 * fbm(a, b, octaves, seed, 2.0, 0.5) - 1.0).abs())
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(value_flat, m)?)?;
    m.add_function(wrap_pyfunction!(fbm_flat, m)?)?;
    m.add_function(wrap_pyfunction!(ridged_flat, m)?)?;
    Ok(())
}

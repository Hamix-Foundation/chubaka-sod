#[pyfunction]
pub fn shader_sources() -> Vec<(String, String)> {
    vec![
        ("common.wgsl".into(), SHADER_COMMON.into()),
        ("main.wgsl".into(), SHADER_MAIN.into()),
        ("shadow.wgsl".into(), SHADER_SHADOW.into()),
        ("ui.wgsl".into(), SHADER_UI.into()),
    ]
}
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Renderer>()?;
    m.add_function(wrap_pyfunction!(shader_sources, m)?)?;
    Ok(())
}

#[pyfunction]
#[pyo3(signature = (api="auto"))]
fn enumerate_adapters<'py>(py: Python<'py>, api: &str) -> PyResult<Vec<Bound<'py, PyDict>>> {
    let api = Api::parse(api)?;
    let mut out = Vec::new();
    for (name, backends) in api.candidates() {
        let inst = crate::gpu::make_instance(backends, None);
        for a in pollster::block_on(inst.enumerate_adapters(backends)) {
            let info = a.get_info();
            let d = adapter_info_dict(py, &info, name)?;
            let lim = a.limits();
            d.set_item("max_texture_2d", lim.max_texture_dimension_2d)?;
            d.set_item("max_uniform_buffer", lim.max_uniform_buffer_binding_size)?;
            let msaa = a
                .get_texture_format_features(wgpu::TextureFormat::Rgba8Unorm)
                .flags
                .sample_count_supported(4)
                && a.get_texture_format_features(crate::gpu::DEPTH_FORMAT)
                    .flags
                    .sample_count_supported(4);
            d.set_item("msaa4", msaa)?;
            out.push(d);
        }
    }
    Ok(out)
}

#[pyfunction]
fn compiled_backends() -> Vec<&'static str> {
    let b = wgpu::Instance::enabled_backend_features();
    let mut v = Vec::new();
    if b.contains(wgpu::Backends::VULKAN) {
        v.push("vulkan");
    }
    if b.contains(wgpu::Backends::GL) {
        v.push("gl");
    }
    if b.contains(wgpu::Backends::METAL) {
        v.push("metal");
    }
    if b.contains(wgpu::Backends::DX12) {
        v.push("dx12");
    }
    v
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<GpuHandle>()?;
    m.add_class::<WindowCore>()?;
    m.add_class::<OffscreenCore>()?;
    m.add_function(wrap_pyfunction!(enumerate_adapters, m)?)?;
    m.add_function(wrap_pyfunction!(compiled_backends, m)?)?;
    m.add("WGPU_VERSION", "30")?;
    m.add("WINIT_VERSION", "0.30")?;
    Ok(())
}

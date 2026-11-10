fn draw(
    rp: &mut wgpu::RenderPass<'_>,
    meshes: &HashMap<u32, GpuMesh>,
    inst: &wgpu::Buffer,
    groups: &[(u32, usize, usize)],
    base: usize,
) {
    for &(gid, start, count) in groups {
        let Some(m) = meshes.get(&gid) else { continue };
        rp.set_vertex_buffer(0, m.vbuf.slice(..));
        rp.set_vertex_buffer(1, inst.slice(((base + start) * STRIDE) as u64..));
        rp.set_index_buffer(m.ibuf.slice(..), wgpu::IndexFormat::Uint32);
        rp.draw_indexed(0..m.index_count, 0, 0..count as u32);
        let _ = m.triangles;
    }
}

@vertex
fn vs(v: VIn) -> @builtin(position) vec4<f32> {
    return g.lvp * vec4<f32>(world_pos(v), 1.0);
}

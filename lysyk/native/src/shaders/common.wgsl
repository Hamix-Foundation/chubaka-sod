struct PL {
    pos_r: vec4<f32>,
    col_i: vec4<f32>,
    dir_c: vec4<f32>,
};

struct Globals {
    vp: mat4x4<f32>,
    lvp: mat4x4<f32>,
    cam: vec4<f32>,
    fog: vec4<f32>,
    sun_dir: vec4<f32>,
    sun_col: vec4<f32>,
    sky_amb: vec4<f32>,
    gnd_amb: vec4<f32>,
    zenith: vec4<f32>,
    horizon: vec4<f32>,
    extra: vec4<f32>,
    water: vec4<f32>,
    shadowp: vec4<f32>,
    lights: array<PL, 8>,
};

@group(0) @binding(0) var<uniform> g: Globals;

struct VIn {
    @location(0) pos: vec3<f32>,
    @location(1) col: vec4<f32>,
    @location(2) ipos: vec3<f32>,
    @location(3) itint: vec4<f32>,
    @location(4) irot: vec4<f32>,
    @location(5) iscale: vec3<f32>,
};

fn wrap(a: f32) -> f32 {
    return a - 6.283185307 * round(a * 0.15915494309);
}

fn world_pos(v: VIn) -> vec3<f32> {
    let s = v.pos * v.iscale;
    let ax = wrap(v.irot.x);
    let ay = wrap(v.irot.y);
    let az = wrap(v.irot.z);
    let sx = sin(ax);
    let cx = cos(ax);
    let sy = sin(ay);
    let cy = cos(ay);
    let sz = sin(az);
    let cz = cos(az);
    return vec3<f32>(
        cz * cy * s.x + (cz * sy * sx - sz * cx) * s.y + (cz * sy * cx + sz * sx) * s.z,
        sz * cy * s.x + (sz * sy * sx + cz * cx) * s.y + (sz * sy * cx - cz * sx) * s.z,
        -sy * s.x + cy * sx * s.y + cy * cx * s.z
    ) + v.ipos;
}

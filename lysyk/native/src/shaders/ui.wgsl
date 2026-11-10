struct U {
    res: vec2<f32>,
    pad: vec2<f32>,
};

@group(0) @binding(0) var<uniform> u: U;
@group(0) @binding(1) var atlas: texture_2d<f32>;
@group(0) @binding(2) var samp: sampler;

struct VIn {
    @builtin(vertex_index) vi: u32,
    @location(0) rect: vec4<f32>,
    @location(1) uvr: vec4<f32>,
    @location(2) col: vec4<f32>,
    @location(3) col2: vec4<f32>,
    @location(4) prm: vec4<f32>,
};

struct VOut {
    @builtin(position) pos: vec4<f32>,
    @location(0) uv: vec2<f32>,
    @location(1) @interpolate(flat) col: vec4<f32>,
    @location(2) @interpolate(flat) col2: vec4<f32>,
    @location(3) loc: vec2<f32>,
    @location(4) @interpolate(flat) size: vec2<f32>,
    @location(5) @interpolate(flat) prm: vec4<f32>,
    @location(6) @interpolate(flat) uvr: vec4<f32>,
};

@vertex
fn vs(i: VIn) -> VOut {
    let x = i.vi == 1u || i.vi == 4u || i.vi == 5u;
    let y = i.vi == 2u || i.vi == 3u || i.vi == 5u;
    let p = vec2<f32>(select(0.0, 1.0, x), select(0.0, 1.0, y));
    let px = i.rect.xy + p * i.rect.zw;
    var o: VOut;
    o.pos = vec4<f32>(px.x / u.res.x * 2.0 - 1.0, 1.0 - px.y / u.res.y * 2.0, 0.0, 1.0);
    o.uv = mix(i.uvr.xy, i.uvr.zw, p);
    o.col = i.col;
    o.col2 = i.col2;
    o.loc = (p - vec2<f32>(0.5)) * i.rect.zw;
    o.size = i.rect.zw;
    o.prm = i.prm;
    o.uvr = i.uvr;
    return o;
}

fn rbox(p: vec2<f32>, ext: vec2<f32>, r: f32) -> f32 {
    let q = abs(p) - ext + vec2<f32>(r);
    return length(max(q, vec2<f32>(0.0))) + min(max(q.x, q.y), 0.0) - r;
}

@fragment
fn fs(i: VOut) -> @location(0) vec4<f32> {
    let tex = textureSample(atlas, samp, i.uv);
    let kind = i.prm.w;
    if (kind < 0.5) {
        return i.col * tex;
    }
    let ext = i.size * 0.5 - vec2<f32>(i.prm.z);
    if (kind > 3.5) {
        let ang = atan2(i.loc.y, i.loc.x);
        let sweep = i.uvr.y;
        var rel = ang - i.uvr.x;
        rel = rel - 6.2831853 * floor(rel / 6.2831853);
        let rr = length(i.loc);
        let thick = i.prm.y;
        let mid = ext.x - thick * 0.5;
        let ring = clamp(0.5 - (abs(rr - mid) - thick * 0.5), 0.0, 1.0);
        let span = clamp((sweep - rel) * mid + 0.5, 0.0, 1.0) * clamp(rel * mid + 0.5, 0.0, 1.0);
        let fillm = clamp((sweep * i.uvr.z - rel) * mid + 0.5, 0.0, 1.0);
        let c = mix(i.col2, i.col, fillm);
        return vec4<f32>(c.rgb, c.a * ring * span);
    }
    let rad = min(i.prm.x, min(ext.x, ext.y));
    let d = rbox(i.loc, ext, rad);
    if (kind < 1.5) {
        let cov = clamp(0.5 - d, 0.0, 1.0);
        let t = clamp((i.loc.y + ext.y) / max(2.0 * ext.y, 1.0), 0.0, 1.0);
        let c = mix(i.col, i.col2, t);
        return vec4<f32>(c.rgb, c.a * cov);
    }
    if (kind < 2.5) {
        let bw = i.prm.y;
        let cov = clamp(0.5 - abs(d + bw * 0.5) + bw * 0.5, 0.0, 1.0);
        return vec4<f32>(i.col.rgb, i.col.a * cov);
    }
    let blur = max(i.prm.z, 1.0);
    let a = 1.0 - smoothstep(-blur * 0.25, blur, d);
    return vec4<f32>(i.col.rgb, i.col.a * a * a);
}

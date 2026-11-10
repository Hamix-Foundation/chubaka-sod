@group(0) @binding(1) var shadow_tex: texture_depth_2d;
@group(0) @binding(2) var shadow_samp: sampler_comparison;

struct VOut {
    @builtin(position) clip: vec4<f32>,
    @location(0) wpos: vec3<f32>,
    @location(1) color: vec3<f32>,
    @location(2) @interpolate(flat) mode: f32,
    @location(3) @interpolate(flat) gloss: f32,
};

@vertex
fn vs(v: VIn) -> VOut {
    let w = world_pos(v);
    var o: VOut;
    o.clip = g.vp * vec4<f32>(w, 1.0);
    o.wpos = w;
    o.color = v.col.rgb * mix(vec3<f32>(1.0), v.itint.rgb, v.col.a);
    o.mode = v.irot.w;
    o.gloss = v.itint.a;
    return o;
}

fn hash3(p: vec3<f32>) -> f32 {
    var q = fract(p * 0.3183099 + vec3<f32>(0.1, 0.2, 0.3));
    q = q * 17.0;
    return fract(q.x * q.y * q.z * (q.x + q.y + q.z));
}

fn sky_color(dir: vec3<f32>) -> vec3<f32> {
    let h = clamp(dir.y, 0.0, 1.0);
    var c = mix(g.horizon.rgb, g.zenith.rgb, pow(h, 0.5));
    let sd = max(dot(dir, g.sun_dir.xyz), 0.0);
    let glow = g.horizon.w;
    c = c + g.sun_col.rgb * (pow(sd, 5.0) * 0.12 * glow + pow(sd, 48.0) * 0.2 * glow);
    c = c + g.sun_col.rgb * smoothstep(0.9993, 0.9998, sd) * 2.0;
    if (g.zenith.w > 0.01 && dir.y > 0.02) {
        let cell = floor(dir * 300.0);
        let r = hash3(cell);
        let tw = step(0.9972, r) * (0.35 + 0.65 * hash3(cell + vec3<f32>(7.0, 3.0, 1.0)));
        c = c + vec3<f32>(tw) * g.zenith.w * smoothstep(0.02, 0.2, dir.y);
    }
    if (dir.y < 0.0) {
        c = mix(c, g.fog.rgb, 1.0 - smoothstep(-0.12, 0.0, dir.y));
    }
    return c;
}

fn apply_fog(c: vec3<f32>, wpos: vec3<f32>) -> vec3<f32> {
    if (g.fog.w <= 0.00001) {
        return c;
    }
    let dv = wpos - g.cam.xyz;
    let dist = length(dv);
    let d = dist * g.fog.w;
    let f = 1.0 - exp(-d * d);
    let vdir = dv / max(dist, 0.001);
    let sc = pow(max(dot(vdir, g.sun_dir.xyz), 0.0), 8.0) * g.extra.z;
    let fc = g.fog.rgb + g.sun_col.rgb * sc * 0.25;
    return mix(c, fc, f);
}

fn soft_clip(c: vec3<f32>) -> vec3<f32> {
    let t = 0.82;
    let over = max(c - vec3<f32>(t), vec3<f32>(0.0));
    return min(c, vec3<f32>(t)) + (1.0 - t) * (1.0 - exp(-over / (1.0 - t)));
}

fn shadow_factor(wpos: vec3<f32>, n: vec3<f32>, ndl: f32) -> f32 {
    let texel = g.shadowp.y;
    let p = wpos + n * (texel * 2.2 * (1.0 - ndl) + texel * 0.8);
    let lc = g.lvp * vec4<f32>(p, 1.0);
    let e = max(abs(lc.x), abs(lc.y));
    if (e > 1.0 || lc.z > 1.0 || lc.z < 0.0) {
        return 1.0;
    }
    let uv = vec2<f32>(lc.x * 0.5 + 0.5, 0.5 - lc.y * 0.5);
    let r = lc.z - g.shadowp.w;
    var s = textureSampleCompareLevel(shadow_tex, shadow_samp, uv, r);
    if (g.shadowp.z > 1.5) {
        let o = g.shadowp.x * 1.35;
        s = s + textureSampleCompareLevel(shadow_tex, shadow_samp, uv + vec2<f32>(o, o * 0.38), r);
        s = s + textureSampleCompareLevel(shadow_tex, shadow_samp, uv + vec2<f32>(-o * 0.38, o), r);
        s = s + textureSampleCompareLevel(shadow_tex, shadow_samp, uv + vec2<f32>(-o, -o * 0.38), r);
        s = s + textureSampleCompareLevel(shadow_tex, shadow_samp, uv + vec2<f32>(o * 0.38, -o), r);
        s = s * 0.2;
    }
    let fade = 1.0 - smoothstep(0.82, 1.0, e);
    return mix(1.0, s, fade);
}

@fragment
fn fs(i: VOut) -> @location(0) vec4<f32> {
    let dx = dpdx(i.wpos);
    let dy = dpdy(i.wpos);
    let tov = g.cam.xyz - i.wpos;
    let mode = i.mode;

    if (mode > 1.5) {
        if (mode < 2.5) {
            return vec4<f32>(sky_color(normalize(-tov)), 1.0);
        }
        if (mode < 3.5) {
            let lc = clamp(g.sky_amb.rgb * 0.9 + g.sun_col.rgb * 0.45, vec3<f32>(0.06), vec3<f32>(1.1));
            return vec4<f32>(i.color * lc, 1.0);
        }
        let t = g.cam.w;
        let p = i.wpos.xz;
        let wn = normalize(vec3<f32>(
            sin(p.x * 0.13 + t * 0.9) * 0.07 + sin(p.y * 0.31 - t * 1.3) * 0.045,
            1.0,
            cos(p.y * 0.11 + t * 0.7) * 0.07 + cos(p.x * 0.27 + t * 1.1) * 0.045));
        let v = normalize(tov);
        let fres = pow(1.0 - max(dot(wn, v), 0.0), 4.0);
        let rf = reflect(-v, wn);
        let env = sky_color(vec3<f32>(rf.x, abs(rf.y), rf.z));
        var wc = mix(g.water.rgb, env, 0.12 + 0.75 * fres);
        let hv = normalize(g.sun_dir.xyz + v);
        wc = wc + g.sun_col.rgb * pow(max(dot(wn, hv), 0.0), 160.0) * 1.3;
        return vec4<f32>(apply_fog(soft_clip(wc * g.extra.y), i.wpos), 1.0);
    }

    if (mode > 0.5) {
        return vec4<f32>(apply_fog(i.color * 1.1, i.wpos), 1.0);
    }

    let dn = cross(dx, dy);
    let ln = length(dn);
    var n = vec3<f32>(0.0, 1.0, 0.0);
    if (ln > 0.000000001) {
        n = dn / ln;
    }
    if (dot(n, tov) < 0.0) {
        n = -n;
    }
    let v = normalize(tov);
    let L = g.sun_dir.xyz;
    let ndl = max(dot(n, L), 0.0);
    var sh = 1.0;
    if (g.sun_col.w > 0.5 && ndl > 0.0) {
        sh = shadow_factor(i.wpos, n, ndl);
    }
    let sun_vis = 1.0 - g.sky_amb.w * (1.0 - sh);
    var lit = mix(g.gnd_amb.rgb, g.sky_amb.rgb, n.y * 0.5 + 0.5) + g.sun_col.rgb * (ndl * sun_vis);
    var lspec = vec3<f32>(0.0);
    let count = u32(g.extra.x);
    for (var k: u32 = 0u; k < count; k = k + 1u) {
        let lp = g.lights[k];
        let to = lp.pos_r.xyz - i.wpos;
        let d2 = dot(to, to);
        let rad = lp.pos_r.w;
        if (d2 < rad * rad) {
            let d = sqrt(d2);
            let ld = to / max(d, 0.001);
            var att = 1.0 - d / rad;
            att = att * att;
            var cone = 1.0;
            if (lp.dir_c.w > -1.5) {
                cone = smoothstep(lp.dir_c.w, lp.dir_c.w + 0.14, dot(-ld, lp.dir_c.xyz));
            }
            let lc = lp.col_i.rgb * (lp.col_i.w * att * cone);
            lit = lit + lc * max(dot(n, ld), 0.0);
            if (i.gloss > 0.01) {
                lspec = lspec + lc * pow(max(dot(n, normalize(ld + v)), 0.0), 36.0);
            }
        }
    }
    var col = i.color * lit;
    if (i.gloss > 0.01) {
        let hv = normalize(L + v);
        let spec = pow(max(dot(n, hv), 0.0), 60.0) * sun_vis * i.gloss;
        let fres = pow(1.0 - max(dot(n, v), 0.0), 3.0);
        let env = sky_color(reflect(-v, n));
        col = mix(col, env, clamp(fres * 0.55 * i.gloss + 0.06 * i.gloss, 0.0, 1.0));
        col = col + g.sun_col.rgb * (spec * 0.9) + lspec * (0.7 * i.gloss);
    }
    col = soft_clip(col * g.extra.y);
    return vec4<f32>(apply_fog(col, i.wpos), 1.0);
}

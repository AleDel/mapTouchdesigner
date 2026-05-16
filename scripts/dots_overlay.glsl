// dots_overlay.glsl
// ──────────────────────────────────────────────────────────────────────────
// GLSL TOP — stamps ramp1 en la posición de cada estación sobre el mapa.
//
// Inputs:
//   0 : mapa de tiles (salida de glsl_tiles_array)
//   1 : posiciones 1D (Nx1 float32, r=sx, g=sy, b=selected, a=quality)
//       — choptol (CHOP to TOP, formato 32-bit float RGBA)
//   2 : ramp1 — textura circular usada como icono de cada dot
//
// Uniforms (GLSL TOP → página "Vectors"):
//   vec0  uDotParams     x=screenW  y=screenH  z=radius(px)  w=dotCount
//   vec1  uDotParamsSel  x=radiusSel (resto sin usar)
//   vec2  uDotColor      rgba tinte color dot normal   (1,1,1,1 = sin tinte)
//   vec3  uDotColorSel   rgba tinte color dot seleccionado
//
// MapaExtension._updateDotsUniforms() actualiza estos valores.

uniform vec4  uDotParams;     // x=screenW  y=screenH  z=radius  w=dotCount
uniform vec4  uDotParamsSel;  // x=radiusSel
uniform vec4  uDotColor;      // rgba tinte normal
uniform vec4  uDotColorSel;   // rgba tinte seleccionado

out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;

    // Fondo: mapa de tiles (input 0)
    vec4 bg = texture(sTD2DInputs[0], uv);
    fragColor = bg;

    float screenW   = uDotParams.x;
    float screenH   = uDotParams.y;
    float radius    = uDotParams.z;
    int   dotCount  = int(uDotParams.w);
    float radiusSel = uDotParamsSel.x;

    for (int i = 0; i < dotCount; i++) {
        // Input 1: un texel por estación (r=sx, g=sy, b=selected, a=quality)
        vec4  d   = texelFetch(sTD2DInputs[1], ivec2(i, 0), 0);
        float sx  = d.r;
        float sy  = d.g;
        float sel = d.b;

        float r = (sel > 0.5) ? radiusSel : radius;

        // Offset en píxeles desde el centro del dot
        float dx = (uv.x - sx) * screenW;
        float dy = (uv.y - sy) * screenH;
        float dist = sqrt(dx * dx + dy * dy);

        // Saltar píxeles fuera del bounding box del dot
        if (abs(dx) > r + 1.0 || abs(dy) > r + 1.0) continue;

        // UV local dentro del cuadrado del dot (0,0=esquina inf-izq, 1,1=esquina sup-der)
        // dx/r en [-1,1] → lx en [0,1]
        float lx = clamp(dx / (r * 2.0) + 0.5, 0.0, 1.0);
        float ly = clamp(dy / (r * 2.0) + 0.5, 0.0, 1.0);

        // Sample ramp1 (input 2) — textura circular del icono
        vec4 ramp = texture(sTD2DInputs[2], vec2(lx, ly));

        // Aplicar tinte de color
        vec4 tint = (sel > 0.5) ? uDotColorSel : uDotColor;
        ramp.rgb *= tint.rgb;
        ramp.a   *= tint.a;

        // Composite over (pre-multiplied alpha)
        fragColor.rgb = ramp.rgb * ramp.a + fragColor.rgb * (1.0 - ramp.a);
        fragColor.a   = ramp.a + fragColor.a * (1.0 - ramp.a);
    }
}

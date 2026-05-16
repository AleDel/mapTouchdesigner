// tiles_atlas.glsl
// ──────────────────────────────────────────────────────────────────────────
// GLSL TOP — compone el mapa muestreando un Texture 2D Array de tiles.
//
// Input 0: tiles_tex3d (Texture 2D Array TOP, type=texture2darray)
//   Layer i = tile en posición row-major: i = (ty - y_min)*grid_w + (tx - x_min)
//   Tiles faltantes en disco = capa negra (moviefilein sin archivo).
//
// Tile sizes:
//   TilesDark: 512 px  |  otros tilesets: 256 px
//   uTileSize = tile_size_real * 2^(zoomFloat - int_zoom)
//
// Setup en TouchDesigner (GLSL TOP -> página "Vectors"):
//   vec0  name="uCenterTile"  x=centerTileX  y=centerTileY
//   vec1  name="uAtlas"       x=x_min  y=y_min  z=grid_w  w=grid_h
//   vec2  name="uScreen"      x=screenW  y=screenH
//   vec3  name="uTileSize"    x=tile_size_px  (px visuales por tile)
//
// MapaExtension._updateGLSLUniforms() actualiza vec0..vec3 en cada pan/zoom.
//
// Nota GLSL: TD auto-declara sTD2DArrayInputs[] cuando GLSL TOP tiene
// type=texture2darray. En GLSL 4.30 (core profile) usar texture() —
// texture2DArray() está deprecada y no es soportada en este modo.

uniform vec2  uCenterTile;  // vec0
uniform vec4  uAtlas;       // vec1: x_min, y_min, grid_w, grid_h
uniform vec2  uScreen;      // vec2
uniform float uTileSize;    // vec3 (solo x)

out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;

    // Offset en px desde el centro (pantalla arriba = norte = menor tile Y)
    float dpx =  (uv.x - 0.5) * uScreen.x;
    float dpy = -(uv.y - 0.5) * uScreen.y;

    // Coordenada mundo-tile (float)
    float wtx = uCenterTile.x + dpx / uTileSize;
    float wty = uCenterTile.y + dpy / uTileSize;

    // Tile entero
    int tx = int(floor(wtx));
    int ty = int(floor(wty));

    // Posición relativa en el grid (row-major)
    int ix = tx - int(uAtlas.x);   // columna (0 = x_min)
    int iy = ty - int(uAtlas.y);   // fila    (0 = y_min = norte)
    int gw = int(uAtlas.z);
    int gh = int(uAtlas.w);

    // Fuera del grid -> negro
    if (ix < 0 || ix >= gw || iy < 0 || iy >= gh) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    // Layer index (row-major: iy varía lento, ix varía rápido)
    float layer = float(iy * gw + ix);

    // UV dentro del tile
    // fract(wtx) : 0=borde oeste, 1=borde este
    // fract(wty) : 0=borde norte, 1=borde sur
    // TD carga PNG con Y-flip -> v=1 es norte, v=0 es sur -> invertir
    float tu = fract(wtx);
    float tv = 1.0 - fract(wty);

    fragColor = texture(sTD2DArrayInputs[0], vec3(tu, tv, layer));
}

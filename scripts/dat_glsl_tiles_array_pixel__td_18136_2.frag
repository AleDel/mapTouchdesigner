// tiles_atlas.glsl
// ──────────────────────────────────────────────────────────────────────────
// GLSL TOP — compone el mapa muestreando un Texture 2D Array de tiles.
//
// Input 0: tiles_tex3d (Texture 2D Array TOP, type=texture2darray)
//   Array COMPACTO: layer 0 = primer tile real, layer 1 = segundo, etc.
//   No hay capas vacías — los gaps (tiles sin archivo) se detectan con uIds.
//
// Tile sizes:
//   TilesDark: 512 px  |  otros tilesets: 256 px
//   uTileSize.x = tile_size_real * 2^(zoomFloat - int_zoom)
//   uTileSize.y = número de tiles reales (uTileCount)
//
// Uniforms (GLSL TOP -> página "Vectors"):
//   vec0  uCenterTile  x=centerTileX  y=centerTileY
//   vec1  uAtlas       x=x_min  y=y_min  z=grid_w  w=grid_h
//   vec2  uScreen      x=screenW  y=screenH
//   vec3  uTileSize    x=tile_size_px  y=tile_count
//   vec4  uIds0        IDs row-major de los tiles reales, capas  0-3
//   vec5  uIds1        IDs row-major de los tiles reales, capas  4-7
//   vec6  uIds2        IDs row-major de los tiles reales, capas  8-11
//   vec7  uIds3        IDs row-major de los tiles reales, capas 12-15
//   vec8  uIds4        IDs row-major de los tiles reales, capas 16-19
//   vec9  uIds5        IDs row-major de los tiles reales, capas 20-23
//   vec10 uIds6        IDs row-major de los tiles reales, capas 24-27
//   vec11 uIds7        IDs row-major de los tiles reales, capas 28-31
//   vec12 uIds8        IDs row-major de los tiles reales, capas 32-35
//
// MapaExtension._updateGLSLUniforms() actualiza vec0..vec12 en cada pan/zoom.

uniform vec2  uCenterTile;  // vec0
uniform vec4  uAtlas;       // vec1: x_min, y_min, grid_w, grid_h
uniform vec2  uScreen;      // vec2
uniform vec4  uTileSize;    // vec3: x=tile_size_px  y=tile_count

// IDs row-major de los tiles reales, empaquetados en vec4s (vec4..vec12)
uniform vec4  uIds0, uIds1, uIds2, uIds3, uIds4;
uniform vec4  uIds5, uIds6, uIds7, uIds8;

out vec4 fragColor;

// Devuelve el row_major_id almacenado en la posición compacta i (0-based)
float getPackedId(int i) {
    int b = i >> 2;   // bloque de 4
    int r = i & 3;    // resto dentro del bloque
    vec4 row;
    if      (b == 0) row = uIds0;
    else if (b == 1) row = uIds1;
    else if (b == 2) row = uIds2;
    else if (b == 3) row = uIds3;
    else if (b == 4) row = uIds4;
    else if (b == 5) row = uIds5;
    else if (b == 6) row = uIds6;
    else if (b == 7) row = uIds7;
    else             row = uIds8;
    return row[r];
}

void main() {
    vec2 uv = vUV.st;

    // Offset en px desde el centro (pantalla arriba = norte = menor tile Y)
    float dpx =  (uv.x - 0.5) * uScreen.x;
    float dpy = -(uv.y - 0.5) * uScreen.y;

    // Coordenada mundo-tile (float)
    float wtx = uCenterTile.x + dpx / uTileSize.x;
    float wty = uCenterTile.y + dpy / uTileSize.x;

    // Tile entero
    int tx = int(floor(wtx));
    int ty = int(floor(wty));

    // Posición relativa en el grid
    int ix = tx - int(uAtlas.x);   // columna (0 = x_min)
    int iy = ty - int(uAtlas.y);   // fila    (0 = y_min = norte)
    int gw = int(uAtlas.z);
    int gh = int(uAtlas.w);

    // Fuera del grid -> negro
    if (ix < 0 || ix >= gw || iy < 0 || iy >= gh) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    // ID row-major de esta posición (1-indexed)
    int row_major_id = iy * gw + ix + 1;

    // Buscar en el array compacto qué capa tiene este ID
    int tile_count = int(uTileSize.y);
    float layer = -1.0;
    for (int i = 0; i < tile_count; i++) {
        if (int(getPackedId(i)) == row_major_id) {
            layer = float(i);
            break;
        }
    }

    // Gap (tile no existe en disco) -> negro
    if (layer < 0.0) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    // UV dentro del tile
    // fract(wtx) : 0=borde oeste, 1=borde este
    // fract(wty) : 0=borde norte, 1=borde sur
    // TD carga PNG con Y-flip -> v=1 es norte, v=0 es sur -> invertir
    float tu = fract(wtx);
    float tv = 1.0 - fract(wty);

    fragColor = texture(sTD2DArrayInputs[0], vec3(tu, tv, layer));
}

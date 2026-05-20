# map2 — Interactive Water Quality Map

TouchDesigner project that visualizes water quality data on an interactive OSM tile map. Built for environmental monitoring in South Korea (2022).

## Description

Displays water quality monitoring stations on a navigable map. Selecting a station shows its normalized parameters (BOD, COD, pH, DO, TN, TP, TOC, SS, EC, Temperature). Data can be filtered by month and date.

## Project Structure

```
map2.toe                   — Main TouchDesigner file
water2022.csv              — Water quality data (Korea, 2022)
scripts/
  MapaExtension.py         — Main extension for the Mapa2 container
  tile_utils.py            — OSM geographic conversions (no TD dependencies)
  panelexec_nav.py         — Navigation: drag, zoom, click
  parexec_filtros.py       — Filter callbacks (month / date)
  script_tiles_callbacks.py
  script_dots_callbacks.py
  script_stations_3d_callbacks.py
  replicator1_callbacks.py
  download_tiles.py        — Tile downloader from multiple sources
  gen_atlas.py             — Tile atlas generator
  estaciones_coords.csv    — Monitoring station coordinates
tiles/                     — Map tilesets (PNG, z/x/y structure)
  TilesDark/
  TilesDark_nl/
  TilesDark2/
  TilesLight/
  TilesSatellite/
  TilesStadiaDark/
  TilesStadiaOsm/
  TilesStadiaSatellite/
  TilesTerrain/
  TilesToner/
  TilesVoyager/
  TilesWaterColor/
35 Free LUTs/              — .CUBE LUT files for color grading
Backup/                    — .toe version history
```

## Architecture

The `Mapa2` container uses a [TouchDesigner Extension](https://docs.derivative.ca/Extensions) (`MapaExt`) that centralizes:

- **Navigation state**: map center (lat/lon), zoom level, screen dimensions
- **Data loading**: `water2022.csv` and `estaciones_coords.csv` are read into memory on init
- **Tile grid**: OSM grid calculation based on the current viewport
- **Filtering**: by month (`01`–`06`) and specific date
- **State machine**: `usable` → `selected` → `animating` → `locked`
- **Parameter normalization**: min/max computed from all data to scale values to 0–1

Geographic logic (lat/lon ↔ tile XY conversions, drag, zoom) lives in `tile_utils.py`, independent of TD.

## Water Quality Parameters

| Channel | Parameter | CSV Column |
|---------|-----------|------------|
| `bod`   | Biochemical Oxygen Demand | 15 |
| `cod`   | Chemical Oxygen Demand | 22 |
| `ph`    | pH | 50 |
| `do`    | Dissolved Oxygen | 31 |
| `tn`    | Total Nitrogen | 58 |
| `tp`    | Total Phosphorus | 60 |
| `toc`   | Total Organic Carbon | 59 |
| `ss`    | Suspended Solids | 54 |
| `ec`    | Electrical Conductivity | 34 |
| `temp`  | Temperature | 57 |

## Downloading Tiles

`scripts/download_tiles.py` downloads tiles locally for offline use. Supports multiple sources:

| Source | Provider | API Key |
|--------|----------|---------|
| `carto_dark` / `carto_light` / `carto_voyager` | CartoDB | Not required |
| `esri_satellite` | Esri | Not required |
| `stadia_dark` / `stadia_sat` / `stadia_osm` | Stadia Maps | Free |
| `stamen_toner` / `stamen_terrain` / `stamen_wc` | Stamen | Free |
| `mapbox_dark` / `mapbox_light` / `mapbox_streets` / `mapbox_sat` | Mapbox | Required |

**Example usage from TD Textport:**
```python
import importlib, sys
sys.path.insert(0, project.folder + '/scripts')
import download_tiles
importlib.reload(download_tiles)
download_tiles.download(
    bbox=(33.0, 124.5, 38.6, 130.0),
    zoom_range=(5, 8),
    source='carto_dark',
    output_dir=project.folder + '/tiles/TilesDark'
)
```

## Requirements

- **TouchDesigner** 2022.x or later
- **Python 3.x** (bundled with TD)
- Tilesets downloaded locally in `tiles/` (or internet access for online mode)

## Usage

1. Open `map2.toe` in TouchDesigner
2. The `MapaExt` extension initializes automatically, loading CSVs and computing the initial tile grid
3. **Navigate**: drag to pan, mouse wheel to zoom
4. **Filter**: use the `Mapa2` container's custom pars (Month, Date)
5. **Change tileset**: `Tileset` custom par on the `Mapa2` container
6. **Select a station**: click a dot to view its water quality parameters

## Development Notes

- Scripts in `scripts/` are portable: they use `project.folder` as the root, no absolute paths
- `tile_utils.py` has no TD imports — it can be tested with standard Python
- The `.CUBE` LUT files in `35 Free LUTs/` can be used with TD's `LookupTOP` operator

---

## 요약 (한국어)

**map2**는 2022년 한국 수질 데이터를 OSM 타일 기반 인터랙티브 지도 위에 시각화하는 TouchDesigner 프로젝트입니다.

- 전국 수질 측정소를 지도에 점(dot)으로 표시하며, 측정소를 클릭하면 BOD, COD, pH, DO, TN, TP, TOC, SS, 전기전도도, 수온 등 10개 수질 지표를 정규화된 값(0–1)으로 확인할 수 있습니다.
- 월별 및 날짜별 필터링을 지원합니다.
- 지도 드래그 및 휠 줌으로 자유롭게 탐색할 수 있습니다.
- TilesDark, TilesLight, TilesSatellite 등 12종의 지도 스타일을 전환할 수 있습니다.
- `scripts/download_tiles.py`를 사용하면 CartoDB, Esri, Stadia, Mapbox 등 다양한 소스에서 타일을 로컬에 저장할 수 있습니다.
- 지리 좌표 변환 로직(`tile_utils.py`)은 TouchDesigner에 의존하지 않아 표준 Python으로 단독 테스트가 가능합니다.

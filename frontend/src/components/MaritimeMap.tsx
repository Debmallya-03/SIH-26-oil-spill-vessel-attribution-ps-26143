import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource, type Map } from "maplibre-gl";
import type { PipelineResponse } from "../api/types";

type LayerKey = "spill" | "backward" | "forward" | "origin" | "vessels";

const LAYERS: Array<[LayerKey, string]> = [
  ["spill", "Oil Spill"],
  ["backward", "Backward Drift"],
  ["forward", "Forward Forecast"],
  ["origin", "Origin Zone"],
  ["vessels", "Candidate Vessels"]
];

interface MaritimeMapProps {
  result: PipelineResponse | null;
  seed?: { latitude: number; longitude: number } | null;
}

export function MaritimeMap({ result, seed }: MaritimeMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const [enabled, setEnabled] = useState<Record<LayerKey, boolean>>({
    spill: true,
    backward: true,
    forward: true,
    origin: true,
    vessels: true
  });

  const geojson = useMemo(() => buildMapFeatures(result, seed, enabled), [result, seed, enabled]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }

    const center: [number, number] = seed ? [seed.longitude, seed.latitude] : [72.8333511352539, 18.5];
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "OpenStreetMap"
          }
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }]
      },
      center,
      zoom: 9,
      pitch: 0
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      map.addSource("investigation", { type: "geojson", data: geojson });
      map.addLayer({
        id: "origin-polygon",
        type: "fill",
        source: "investigation",
        filter: ["==", ["get", "kind"], "origin_polygon"],
        paint: {
          "fill-color": "#22d3ee",
          "fill-opacity": 0.18
        }
      });
      map.addLayer({
        id: "backward-line",
        type: "line",
        source: "investigation",
        filter: ["==", ["get", "kind"], "backward"],
        paint: {
          "line-color": "#67e8f9",
          "line-width": 3,
          "line-dasharray": [2, 2]
        }
      });
      map.addLayer({
        id: "forward-line",
        type: "line",
        source: "investigation",
        filter: ["==", ["get", "kind"], "forward"],
        paint: {
          "line-color": "#f59e0b",
          "line-width": 3
        }
      });
      map.addLayer({
        id: "points",
        type: "circle",
        source: "investigation",
        filter: ["in", ["get", "kind"], ["literal", ["seed", "origin"]]],
        paint: {
          "circle-radius": ["case", ["==", ["get", "kind"], "origin"], 8, 6],
          "circle-color": ["case", ["==", ["get", "kind"], "origin"], "#22d3ee", "#f59e0b"],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#06111f"
        }
      });
    });
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) {
      return;
    }
    const source = map.getSource("investigation") as GeoJSONSource | undefined;
    source?.setData(geojson);
    const bounds = featureBounds(geojson);
    if (bounds) {
      map.fitBounds(bounds, { padding: 80, maxZoom: 11, duration: 500 });
    }
  }, [geojson]);

  return (
    <section className="map-shell">
      <div className="map-toolbar">
        {LAYERS.map(([key, label]) => (
          <label key={key} className="layer-toggle">
            <input
              type="checkbox"
              checked={enabled[key]}
              onChange={(event) => setEnabled((current) => ({ ...current, [key]: event.target.checked }))}
            />
            {label}
          </label>
        ))}
      </div>
      <div ref={containerRef} className="map-canvas" />
      <div className="map-note">
        Map plots only backend geographic coordinates. Module A image-space masks are not georeferenced here.
      </div>
    </section>
  );
}

function buildMapFeatures(result: PipelineResponse | null, seed: MaritimeMapProps["seed"], enabled: Record<LayerKey, boolean>) {
  const features: GeoJSON.Feature[] = [];
  if (enabled.spill && seed) {
    features.push({
      type: "Feature",
      properties: { kind: "seed", label: "Spill seed" },
      geometry: { type: "Point", coordinates: [seed.longitude, seed.latitude] }
    });
  }
  if (enabled.origin && result?.drift?.origin_area) {
    features.push({
      type: "Feature",
      properties: { kind: "origin_polygon", label: "Estimated origin zone" },
      geometry: result.drift.origin_area
    });
  }
  if (enabled.origin && result?.drift?.origin_centroid) {
    features.push({
      type: "Feature",
      properties: { kind: "origin", label: "Estimated origin" },
      geometry: {
        type: "Point",
        coordinates: [result.drift.origin_centroid.longitude, result.drift.origin_centroid.latitude]
      }
    });
  }
  if (enabled.backward && result?.drift?.backward_path?.coordinates?.length) {
    features.push({
      type: "Feature",
      properties: { kind: "backward", label: "Backward hindcast" },
      geometry: result.drift.backward_path
    });
  }
  if (enabled.forward && result?.drift?.forward_path?.coordinates?.length) {
    features.push({
      type: "Feature",
      properties: { kind: "forward", label: "Forward forecast" },
      geometry: result.drift.forward_path
    });
  }
  return { type: "FeatureCollection", features } as GeoJSON.FeatureCollection;
}

function featureBounds(collection: GeoJSON.FeatureCollection): maplibregl.LngLatBounds | null {
  const coords: number[][] = [];
  collection.features.forEach((feature) => collectCoordinates(feature.geometry, coords));
  if (!coords.length) {
    return null;
  }
  const bounds = new maplibregl.LngLatBounds(coords[0] as [number, number], coords[0] as [number, number]);
  coords.forEach((coordinate) => bounds.extend(coordinate as [number, number]));
  return bounds;
}

function collectCoordinates(geometry: GeoJSON.Geometry | null, output: number[][]) {
  if (!geometry) {
    return;
  }
  if (geometry.type === "Point") {
    output.push(geometry.coordinates as number[]);
  } else if (geometry.type === "LineString") {
    output.push(...(geometry.coordinates as number[][]));
  } else if (geometry.type === "Polygon") {
    geometry.coordinates.forEach((ring) => output.push(...ring));
  }
}

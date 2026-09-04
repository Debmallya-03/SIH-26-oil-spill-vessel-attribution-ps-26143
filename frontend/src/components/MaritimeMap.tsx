import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource, type Map } from "maplibre-gl";
import type { PipelineResponse, VesselScore } from "../api/types";

type LayerKey = "spill" | "backward" | "forward" | "origin" | "vessels";

const LAYERS: Array<[LayerKey, string]> = [
  ["spill", "Oil Spill"],
  ["backward", "Hindcasting"],
  ["forward", "Forward Forecast"],
  ["origin", "Origin Zone"],
  ["vessels", "Candidate Vessels"]
];

const LAYER_COLORS: Record<LayerKey, string> = {
  spill: "#f59e0b",
  backward: "#67e8f9",
  forward: "#f59e0b",
  origin: "#22d3ee",
  vessels: "#94a3b8"
};

interface MaritimeMapProps {
  result: PipelineResponse | null;
  seed?: { latitude: number; longitude: number } | null;
  compact?: boolean;
}

export function MaritimeMap({ result, seed, compact = false }: MaritimeMapProps) {
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
  const vesselTrajectoriesAvailable = Boolean(result?.attribution?.suspects?.some((candidate) => (candidate.trajectory?.length ?? 0) >= 2));
  const unavailableLayers = new Set<LayerKey>(vesselTrajectoriesAvailable ? [] : ["vessels"]);

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
        id: "vessel-lines",
        type: "line",
        source: "investigation",
        filter: ["==", ["get", "kind"], "vessel_track"],
        paint: {
          "line-color": "#94a3b8",
          "line-width": ["case", ["==", ["get", "rank"], 1], 3, 2],
          "line-opacity": ["case", ["<=", ["get", "rank"], 3], 0.82, 0.42]
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
      map.addLayer({
        id: "vessel-points",
        type: "circle",
        source: "investigation",
        filter: ["==", ["get", "kind"], "vessel_marker"],
        paint: {
          "circle-radius": ["case", ["==", ["get", "rank"], 1], 7, 5],
          "circle-color": "#94a3b8",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#06111f"
        }
      });
      map.on("click", "vessel-points", (event) => {
        const feature = event.features?.[0];
        const coordinates = feature?.geometry.type === "Point" ? [...feature.geometry.coordinates] as [number, number] : null;
        if (!feature?.properties || !coordinates) {
          return;
        }
        new maplibregl.Popup()
          .setLngLat(coordinates)
          .setHTML(vesselPopupHtml(feature.properties))
          .addTo(map);
      });
      map.on("mouseenter", "vessel-points", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "vessel-points", () => {
        map.getCanvas().style.cursor = "";
      });
      map.resize();
      const bounds = featureBounds(geojson);
      if (bounds) {
        map.fitBounds(bounds, { padding: 60, maxZoom: 11, duration: 0 });
      }
    });
    mapRef.current = map;

    const resizeObserver = new ResizeObserver(() => {
      map.resize();
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
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
    map.resize();
    const bounds = featureBounds(geojson);
    if (bounds) {
      map.fitBounds(bounds, { padding: 80, maxZoom: 11, duration: 500 });
    }
  }, [geojson]);

  return (
    <section className={compact ? "map-shell map-shell-compact" : "map-shell"}>
      {!compact && (
        <div className="map-toolbar">
          {LAYERS.map(([key, label]) => (
            <label
              key={key}
              className={unavailableLayers.has(key) ? "layer-toggle layer-toggle-disabled" : "layer-toggle"}
              title={unavailableLayers.has(key) ? "Backend vessel rankings do not include geographic track coordinates." : undefined}
            >
              <input
                type="checkbox"
                checked={enabled[key]}
                disabled={unavailableLayers.has(key)}
                onChange={(event) => setEnabled((current) => ({ ...current, [key]: event.target.checked }))}
              />
              <span className="legend-dot" style={{ background: LAYER_COLORS[key] }} />
              {label}
            </label>
          ))}
        </div>
      )}
      <div ref={containerRef} className="map-canvas" />
      {!compact && (
        <div className="map-note">
          Map plots only backend geographic coordinates. Module A image-space masks are not georeferenced, and vessel tracks are hidden until backend AIS coordinates are exposed.
        </div>
      )}
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
  if (enabled.vessels && result?.attribution?.suspects?.length) {
    result.attribution.suspects.slice(0, 5).forEach((candidate) => {
      const trajectory = candidate.trajectory ?? [];
      if (trajectory.length < 2) {
        return;
      }
      features.push({
        type: "Feature",
        properties: {
          kind: "vessel_track",
          label: `#${candidate.rank ?? "-"} ${candidate.vessel_name}`,
          rank: candidate.rank ?? 999,
          mmsi: candidate.mmsi,
          trajectory_source: candidate.trajectory_source ?? "not_reported"
        },
        geometry: {
          type: "LineString",
          coordinates: trajectory.map((point) => [point.longitude, point.latitude])
        }
      });
      const marker = relevantTrajectoryPoint(candidate);
      if (marker) {
        features.push({
          type: "Feature",
          properties: {
            kind: "vessel_marker",
            label: `#${candidate.rank ?? "-"} ${candidate.vessel_name}`,
            rank: candidate.rank ?? 999,
            mmsi: candidate.mmsi,
            score: candidate.score,
            priority: candidate.priority ?? "not_reported",
            timestamp: marker.timestamp,
            distance_km: candidate.minimum_distance_km ?? null,
            sog: marker.sog ?? null,
            cog: marker.cog ?? null,
            trajectory_source: candidate.trajectory_source ?? "not_reported"
          },
          geometry: {
            type: "Point",
            coordinates: [marker.longitude, marker.latitude]
          }
        });
      }
    });
  }
  return { type: "FeatureCollection", features } as GeoJSON.FeatureCollection;
}

function relevantTrajectoryPoint(candidate: VesselScore) {
  const trajectory = candidate.trajectory ?? [];
  if (!trajectory.length) {
    return null;
  }
  if (!candidate.nearest_approach_time) {
    return trajectory[0];
  }
  const target = new Date(candidate.nearest_approach_time).getTime();
  return trajectory.reduce((best, point) => {
    const bestDelta = Math.abs(new Date(best.timestamp).getTime() - target);
    const pointDelta = Math.abs(new Date(point.timestamp).getTime() - target);
    return pointDelta < bestDelta ? point : best;
  }, trajectory[0]);
}

function vesselPopupHtml(properties: Record<string, unknown>) {
  return `
    <strong>${escapeHtml(String(properties.label ?? "Candidate vessel"))}</strong><br />
    MMSI: ${escapeHtml(String(properties.mmsi ?? "not reported"))}<br />
    Priority: ${escapeHtml(String(properties.priority ?? "not reported"))}<br />
    Score: ${escapeHtml(String(properties.score ?? "not reported"))}<br />
    Time: ${escapeHtml(String(properties.timestamp ?? "not reported"))}<br />
    Distance: ${properties.distance_km == null ? "not reported" : `${Number(properties.distance_km).toFixed(2)} km`}<br />
    SOG/COG: ${properties.sog == null ? "n/a" : Number(properties.sog).toFixed(1)} / ${properties.cog == null ? "n/a" : Number(properties.cog).toFixed(0)}<br />
    Source: ${escapeHtml(String(properties.trajectory_source ?? "not reported"))}
  `;
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (char) => {
    const entities: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return entities[char];
  });
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

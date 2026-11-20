/**
 * Adaptador aislado de proveedor de mapas para Luca (# ADR-005 / Prompt 5 Sección 2).
 *
 * ÚNICO archivo de front-end que conoce los detalles de MapLibre GL JS + Geoapify.
 * Para cambiar a MapTiler, Stadia Maps o TomTom basta ajustar este módulo y
 * `apps/comercios/geo_proxy.py`.
 */
import * as maplibregl from "/static/vendor/maplibre-gl/maplibre-gl.mjs";

// Configurar worker local compatible con CSP estricta (sin blob:)
if (typeof maplibregl.setWorkerUrl === "function") {
  maplibregl.setWorkerUrl("/static/vendor/maplibre-gl/maplibre-gl-worker.mjs");
}

export const ATRIBUCION_OBLIGATORIA =
  'Powered by <a href="https://www.geoapify.com/" target="_blank" rel="noopener noreferrer">Geoapify</a> · © OpenMapTiles · © OpenStreetMap contributors';

export function soportaWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext("webgl2") || canvas.getContext("webgl") || canvas.getContext("experimental-webgl"))
    );
  } catch (_) {
    return false;
  }
}

export function crearMapaVectorial({ container, config, embebido = false }) {
  const centro = config.centroide || { lat: -33.491, lng: -70.6745 };
  const mapa = new maplibregl.Map({
    container,
    style: config.estilo_url,
    center: [centro.lng, centro.lat],
    zoom: embebido ? 13.3 : 13.8,
    minZoom: 12,
    maxZoom: 18,
    maxBounds: config.max_bounds || [[-70.72, -33.53], [-70.63, -33.45]],
    attributionControl: false,
    cooperativeGestures: Boolean(embebido),
  });

  // Atribución obligatoria siempre visible y no colapsada (# Sección 2.1)
  mapa.addControl(
    new maplibregl.AttributionControl({
      compact: false,
      customAttribution: ATRIBUCION_OBLIGATORIA,
    }),
    "bottom-right"
  );
  mapa.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

  return { mapa, maplibregl };
}

export { maplibregl };

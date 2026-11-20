/**
 * Mapa público accesible de comercios de Pedro Aguirre Cerda con MapLibre GL JS + Geoapify
 * y datos GeoJSON propios desde PostGIS (# REQ-05, REQ-11, REQ-12 / Prompt 5 Sección 2).
 *
 * Características clave:
 * - Carga perezosa (IntersectionObserver).
 * - Degradación automática elegante al listado accesible si falta clave, falla WebGL o hay error.
 * - Clustering nativo GeoJSON + marcadores HTML `<button>` accesibles (enfocables por teclado).
 * - Pines con ícono + color + texto (y precio + "▼ Más barato" si hay producto seleccionado).
 * - Popup accesible (Esc cierra y devuelve foco) con logo/monograma, horario, tel:, "Cómo llegar"
 *   (enlaces a Google Maps, Waze y geo: sin usar Google Maps API).
 * - Botón "Cerca de mí" con aviso de privacidad (no guarda ubicación).
 */
import { crearMapaVectorial, soportaWebGL } from "./proveedor-mapas.js";

const ICONOS_TIPO = {
  SUPERMERCADO: { icono: "🛒", bg: "#12385C" },
  ALMACEN: { icono: "🏪", bg: "#0B6E70" },
  MINIMARKET: { icono: "🏬", bg: "#1D6FB8" },
  FARMACIA: { icono: "💊", bg: "#C62828" },
  FERIA: { icono: "🥬", bg: "#187540" },
  PANADERIA: { icono: "🥖", bg: "#D98A00" },
  CARNICERIA: { icono: "🥩", bg: "#C8401C" },
  VERDULERIA: { icono: "🍎", bg: "#187540" },
  OTRO: { icono: "📍", bg: "#12385C" },
};

function formatearCLP(valor) {
  return `$${Number(valor).toLocaleString("es-CL")}`;
}

function escaparHtml(str) {
  return String(str || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function iniciarMapaPublico() {
  const contenedor = document.getElementById("mapa-luca");
  if (!contenedor) return;

  const embebido = contenedor.dataset.embebido === "1";
  const btnMapa = document.getElementById("btn-ver-mapa");
  const btnLista = document.getElementById("btn-ver-lista");
  const panelMapa = document.getElementById("panel-mapa");
  const panelLista = document.getElementById("panel-lista");
  const avisoMapa = document.getElementById("aviso-estado-mapa");
  const btnCerca = document.getElementById("btn-mi-ubicacion");
  const estadoUbicacion = document.getElementById("estado-ubicacion");

  let mapaInstancia = null;
  let mlLib = null;
  let marcadoresHtml = [];
  let popupActivo = null;
  let inicializado = false;
  let ubicacionUsuario = null;

  function mostrarFallbackLista(mensaje) {
    if (avisoMapa) {
      avisoMapa.textContent = mensaje;
      avisoMapa.classList.remove("hidden");
    }
    if (panelMapa && panelLista) {
      panelMapa.classList.add("hidden");
      panelLista.classList.remove("hidden");
      btnMapa?.setAttribute("aria-pressed", "false");
      btnLista?.setAttribute("aria-pressed", "true");
    } else if (contenedor) {
      contenedor.innerHTML = `<div class="p-6 text-center text-sm font-semibold text-marino-900 bg-ambar-100 rounded-xl h-full flex flex-col items-center justify-center gap-2"><p>${escaparHtml(mensaje)}</p><a href="/mapa/?vista=lista" class="btn-primario !py-2 !px-4 text-sm">Ver listado completo de comercios</a></div>`;
    }
  }

  function cambiarVista(modo) {
    if (!panelMapa || !panelLista) return;
    const esMapa = modo === "mapa";
    panelMapa.classList.toggle("hidden", !esMapa);
    panelLista.classList.toggle("hidden", esMapa);
    btnMapa?.setAttribute("aria-pressed", esMapa ? "true" : "false");
    btnLista?.setAttribute("aria-pressed", esMapa ? "false" : "true");
    if (esMapa && mapaInstancia) {
      setTimeout(() => mapaInstancia.resize(), 120);
    }
  }

  btnMapa?.addEventListener("click", () => cambiarVista("mapa"));
  btnLista?.addEventListener("click", () => cambiarVista("lista"));

  function construirPopupHtml(p, lng, lat) {
    const logoHtml = p.logo_url
      ? `<img src="${escaparHtml(p.logo_url)}" alt="Logo de ${escaparHtml(p.comercio)}" width="40" height="40" class="w-10 h-10 rounded-lg object-contain border border-gris-200 bg-white">`
      : `<span class="w-10 h-10 rounded-lg inline-flex items-center justify-center text-white font-bold text-sm shrink-0" style="background:${escaparHtml(p.color_monograma)}">${escaparHtml(p.iniciales)}</span>`;

    const precioHtml = p.precio
      ? `<div class="mt-2 p-2 rounded-lg ${p.es_mas_barato ? "bg-verde-100 text-verde-700" : "bg-marino-100 text-marino-900"} font-bold text-sm">
           ${p.es_mas_barato ? "▼ Más barato: " : "Precio: "}${formatearCLP(p.precio)}
           <span class="block text-xs font-normal">Obs: ${escaparHtml(p.precio_fecha)} ${p.precio_condiciones ? "· " + escaparHtml(p.precio_condiciones) : ""}</span>
         </div>`
      : "";

    const telHtml = p.telefono
      ? `<p class="text-xs mt-1"><a href="tel:${escaparHtml(p.telefono)}" class="underline font-bold text-marino-700">📞 ${escaparHtml(p.telefono)}</a></p>`
      : "";

    const gmaps = `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
    const waze = `https://waze.com/ul?ll=${lat},${lng}&navigate=yes`;

    return `
      <div class="font-sans text-gris-900 max-w-xs space-y-1.5" role="dialog" aria-label="Detalle de ${escaparHtml(p.nombre)}">
        <div class="flex items-center gap-2.5">
          ${logoHtml}
          <div>
            <strong class="text-marino-900 text-base leading-tight block">${escaparHtml(p.nombre)}</strong>
            <span class="text-xs font-bold text-turquesa-700">${escaparHtml(p.tipo_texto)} · ${escaparHtml(p.sector)}</span>
          </div>
        </div>
        <p class="text-xs text-gris-700">📍 ${escaparHtml(p.direccion)}</p>
        <p class="text-xs text-gris-700">🕒 ${escaparHtml(p.horario)}</p>
        ${p.distancia_texto ? `<p class="text-xs font-bold text-turquesa-700">${escaparHtml(p.distancia_texto)}</p>` : ""}
        ${telHtml}
        ${precioHtml}
        <div class="flex flex-wrap gap-1.5 pt-2">
          <a href="${escaparHtml(p.url)}" class="px-3 py-1.5 rounded-lg bg-marino-700 text-white font-bold text-xs">Ver precios</a>
          <a href="${gmaps}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1.5 rounded-lg border border-marino-700 text-marino-900 font-bold text-xs">Google Maps ↗</a>
          <a href="${waze}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1.5 rounded-lg border border-turquesa-700 text-turquesa-700 font-bold text-xs">Waze ↗</a>
        </div>
      </div>
    `;
  }

  function limpiarMarcadores() {
    marcadoresHtml.forEach((m) => m.remove());
    marcadoresHtml = [];
  }

  function renderizarMarcadoresAccesibles(features) {
    limpiarMarcadores();
    if (!mapaInstancia || !mlLib) return;

    features.slice(0, 150).forEach((f) => {
      const p = f.properties;
      const [lng, lat] = f.geometry.coordinates;
      const meta = ICONOS_TIPO[p.tipo] || ICONOS_TIPO.OTRO;

      const btn = document.createElement("button");
      btn.type = "button";
      const bg = p.es_mas_barato ? "#187540" : meta.bg;
      btn.style.backgroundColor = bg;
      btn.className =
        "min-h-[36px] px-2.5 py-1 rounded-full text-white font-bold text-xs shadow-md border-2 border-white flex items-center gap-1 cursor-pointer focus-visible:outline focus-visible:outline-3 focus-visible:outline-ambar-400";
      btn.setAttribute(
        "aria-label",
        `${p.nombre}, ${p.tipo_texto}${p.distancia_texto ? ", " + p.distancia_texto : ""}${p.precio ? ", " + formatearCLP(p.precio) : ""}`
      );
      btn.innerHTML = p.precio
        ? `<span aria-hidden="true">${p.es_mas_barato ? "▼" : meta.icono}</span><span>${formatearCLP(p.precio)}</span>`
        : `<span aria-hidden="true">${meta.icono}</span><span class="max-w-[110px] truncate">${escaparHtml(p.comercio)}</span>`;

      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        if (popupActivo) popupActivo.remove();
        popupActivo = new mlLib.Popup({ closeOnClick: true, maxWidth: "300px" })
          .setLngLat([lng, lat])
          .setHTML(construirPopupHtml(p, lng, lat))
          .addTo(mapaInstancia);
        popupActivo.on("close", () => btn.focus());

        // Sincronizar con elemento de la lista si existe
        document.querySelectorAll("[data-sucursal-id]").forEach((card) => {
          const coincide = card.dataset.sucursalId === String(p.id);
          card.classList.toggle("ring-4", coincide);
          card.classList.toggle("ring-ambar-400", coincide);
        });
      });

      const marker = new mlLib.Marker({ element: btn, anchor: "bottom" })
        .setLngLat([lng, lat])
        .addTo(mapaInstancia);
      marcadoresHtml.push(marker);
    });
  }

  async function cargarSucursalesEnMapa() {
    if (!mapaInstancia) return;
    const params = new URLSearchParams(window.location.search);
    const bounds = mapaInstancia.getBounds();
    if (bounds && !ubicacionUsuario) {
      params.set("bbox", `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`);
    }
    if (ubicacionUsuario) {
      params.set("lat", String(ubicacionUsuario.lat));
      params.set("lng", String(ubicacionUsuario.lng));
    }

    try {
      const resp = await fetch(`/api/mapa/sucursales/?${params.toString()}`);
      if (!resp.ok) return;
      const geojson = await resp.json();

      const fuente = mapaInstancia.getSource("sucursales-luca");
      if (fuente) {
        fuente.setData(geojson);
      }

      // Mostrar marcadores HTML accesibles cuando el zoom permite ver locales sin saturar
      if (mapaInstancia.getZoom() >= 13.2 || geojson.features.length <= 40) {
        renderizarMarcadoresAccesibles(geojson.features);
      } else {
        limpiarMarcadores();
      }

      // Actualizar distancias en la vista de lista
      geojson.features.forEach((f) => {
        const p = f.properties;
        const card = document.querySelector(`[data-sucursal-id="${p.id}"]`);
        const dest = card?.querySelector("[data-distancia-texto]");
        if (dest && p.distancia_texto) dest.textContent = p.distancia_texto;
      });
    } catch (_) {
      /* Red temporalmente no disponible */
    }
  }

  async function arrancarMapa() {
    if (inicializado) return;
    inicializado = true;

    if (!soportaWebGL()) {
      mostrarFallbackLista("Tu navegador no soporta gráficos WebGL para el mapa interactivo. Te mostramos el listado completo de comercios.");
      return;
    }

    try {
      const resp = await fetch("/api/mapa/config/");
      if (!resp.ok) throw new Error("No se pudo cargar la configuración del mapa");
      const config = await resp.json();

      if (!config.tiene_clave_mapa || !config.estilo_url) {
        mostrarFallbackLista("El mapa interactivo requiere configurar GEOAPIFY_KEY_NAVEGADOR. Mientras tanto puedes usar el listado completo con direcciones y enlaces 'Cómo llegar'.");
        return;
      }

      const { mapa, maplibregl } = crearMapaVectorial({ container: contenedor, config, embebido });
      mapaInstancia = mapa;
      mlLib = maplibregl;

      mapa.on("error", () => {
        if (!mapa.isStyleLoaded()) {
          mostrarFallbackLista("No pudimos cargar el mapa en este momento (conexión o cuota del proveedor). Te mostramos el listado equivalente.");
        }
      });

      mapa.on("load", () => {
        // 1. Dibujar contorno discreto del límite comunal de Pedro Aguirre Cerda
        if (config.limite_geojson) {
          mapa.addSource("limite-comuna", { type: "geojson", data: config.limite_geojson });
          mapa.addLayer({
            id: "limite-comuna-linea",
            type: "line",
            source: "limite-comuna",
            paint: { "line-color": "#12385C", "line-width": 2.5, "line-dasharray": [3, 2] },
          });
        }

        // 2. Fuente GeoJSON con clustering nativo de MapLibre
        mapa.addSource("sucursales-luca", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
          cluster: true,
          clusterMaxZoom: 13,
          clusterRadius: 48,
        });
        mapa.addLayer({
          id: "clusters-circulos",
          type: "circle",
          source: "sucursales-luca",
          filter: ["has", "point_count"],
          paint: {
            "circle-color": "#12385C",
            "circle-radius": 20,
            "circle-stroke-width": 3,
            "circle-stroke-color": "#F5A623",
          },
        });
        mapa.addLayer({
          id: "clusters-conteo",
          type: "symbol",
          source: "sucursales-luca",
          filter: ["has", "point_count"],
          layout: { "text-field": "{point_count_abbreviated}", "text-size": 13 },
          paint: { "text-color": "#FFFFFF" },
        });

        cargarSucursalesEnMapa();
      });

      mapa.on("moveend", () => cargarSucursalesEnMapa());

      // Sincronización lista -> mapa: tocar un ítem centra el mapa en la sucursal
      document.querySelectorAll("[data-centrar-sucursal]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const lat = parseFloat(btn.dataset.lat);
          const lng = parseFloat(btn.dataset.lng);
          cambiarVista("mapa");
          mapa.flyTo({ center: [lng, lat], zoom: 16, essential: true });
        });
      });
    } catch (_) {
      mostrarFallbackLista("No fue posible iniciar el mapa interactivo. Te mostramos el listado completo de comercios.");
    }
  }

  // Botón "Cerca de mí" (# Sección 2.2: sin guardar ubicación)
  btnCerca?.addEventListener("click", () => {
    if (!navigator.geolocation) {
      if (estadoUbicacion) estadoUbicacion.textContent = "Tu navegador no soporta geolocalización. Usa los filtros por sector.";
      return;
    }
    if (estadoUbicacion) estadoUbicacion.textContent = "Obteniendo tu ubicación (solo para ordenar resultados; no se guarda)…";
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        ubicacionUsuario = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        if (estadoUbicacion) estadoUbicacion.textContent = "Mostrando los comercios más cercanos a ti (tu ubicación no se almacena).";
        if (mapaInstancia) {
          mapaInstancia.flyTo({ center: [ubicacionUsuario.lng, ubicacionUsuario.lat], zoom: 15 });
          cargarSucursalesEnMapa();
        }
      },
      () => {
        if (estadoUbicacion) estadoUbicacion.textContent = "No otorgaste permiso de ubicación. Puedes buscar por dirección o filtrar por sector.";
      }
    );
  });

  // Carga perezosa mediante IntersectionObserver (# Sección 2.1)
  if ("IntersectionObserver" in window && embebido) {
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          obs.disconnect();
          arrancarMapa();
        }
      },
      { rootMargin: "120px" }
    );
    obs.observe(contenedor);
  } else {
    arrancarMapa();
  }
}

document.addEventListener("DOMContentLoaded", iniciarMapaPublico);

/**
 * Combobox ARIA accesible de autocompletado de direcciones + mapa pequeño MapLibre
 * con pin arrastrable y alternativa operable 100% por teclado (# REQ-02, REQ-12 / Prompt 5).
 */
import { crearMapaVectorial, soportaWebGL } from "./proveedor-mapas.js";

function iniciarBuscadorUbicacion() {
  const inputDir = document.getElementById("id_direccion");
  const listaBox = document.getElementById("lista-sugerencias-direccion");
  const anuncioAria = document.getElementById("anuncio-direccion-aria");
  const inputLat = document.getElementById("id_latitud");
  const inputLng = document.getElementById("id_longitud");
  const inputDirNorm = document.getElementById("id_direccion_normalizada");
  const inputOrigen = document.getElementById("id_origen_coordenada");
  const inputAjuste = document.getElementById("id_requiere_ajuste");
  const avisoPrecision = document.getElementById("aviso-precision-ubicacion");
  const panelConfirmarInv = document.getElementById("confirmar-direccion-inversa");
  const textoInv = document.getElementById("texto-direccion-inversa");
  const btnAceptarInv = document.getElementById("btn-aceptar-inversa");
  const contenedorMapa = document.getElementById("mapa-selector-sucursal");

  if (!inputDir || !inputLat || !inputLng) return;

  let temporizador = null;
  let controladorAbort = null;
  let sugerenciasActuales = [];
  let indiceActivo = -1;
  let marcador = null;
  let mapaSel = null;
  let direccionSugeridaInversa = "";

  function anunciar(texto) {
    if (anuncioAria) anuncioAria.textContent = texto;
  }

  function actualizarCoordenadas(lat, lng, origen = "MANUAL") {
    inputLat.value = Number(lat).toFixed(6);
    inputLng.value = Number(lng).toFixed(6);
    if (inputOrigen) inputOrigen.value = origen;
    if (marcador) marcador.setLngLat([Number(lng), Number(lat)]);
    if (mapaSel) mapaSel.flyTo({ center: [Number(lng), Number(lat)], zoom: Math.max(mapaSel.getZoom(), 16) });
  }

  function cerrarLista() {
    if (!listaBox) return;
    listaBox.classList.add("hidden");
    listaBox.innerHTML = "";
    inputDir.setAttribute("aria-expanded", "false");
    inputDir.removeAttribute("aria-activedescendant");
    indiceActivo = -1;
  }

  function elegirSugerencia(item) {
    inputDir.value = item.direccion || inputDir.value;
    if (inputDirNorm) inputDirNorm.value = item.direccion || "";
    actualizarCoordenadas(item.lat, item.lng, "GEOAPIFY");
    if (inputAjuste) inputAjuste.checked = Boolean(item.requiere_ajuste);
    if (avisoPrecision) {
      if (item.requiere_ajuste) {
        avisoPrecision.textContent = "⚠ Ubicación aproximada: por favor ajusta el pin hasta la puerta del local.";
        avisoPrecision.classList.remove("hidden");
      } else {
        avisoPrecision.classList.add("hidden");
      }
    }
    anunciar(`Dirección seleccionada: ${item.direccion}`);
    cerrarLista();
  }

  function renderizarSugerencias(items) {
    if (!listaBox) return;
    sugerenciasActuales = items;
    indiceActivo = -1;
    if (!items.length) {
      cerrarLista();
      anunciar("No se encontraron sugerencias. Puedes escribir una referencia o ubicar el pin.");
      return;
    }
    listaBox.innerHTML = "";
    items.forEach((it, idx) => {
      const li = document.createElement("li");
      li.id = `sug-dir-${idx}`;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", "false");
      li.className = "px-4 py-3 cursor-pointer hover:bg-marino-100 border-b border-gris-200 text-sm font-semibold text-marino-900";
      li.textContent = it.direccion;
      li.addEventListener("mousedown", (ev) => {
        ev.preventDefault();
        elegirSugerencia(it);
      });
      listaBox.appendChild(li);
    });
    listaBox.classList.remove("hidden");
    inputDir.setAttribute("aria-expanded", "true");
    anunciar(`${items.length} sugerencias disponibles. Usa flechas arriba y abajo para elegir.`);
  }

  // Combobox con debounce 300 ms y cancelación de solicitudes en curso (# Sección 2.3)
  inputDir.addEventListener("input", () => {
    clearTimeout(temporizador);
    const q = inputDir.value.trim();
    if (q.length < 3) {
      cerrarLista();
      return;
    }
    temporizador = setTimeout(async () => {
      if (controladorAbort) controladorAbort.abort();
      controladorAbort = new AbortController();
      try {
        const resp = await fetch(`/api/geo/autocompletar/?q=${encodeURIComponent(q)}`, {
          signal: controladorAbort.signal,
        });
        const data = await resp.json();
        if (data.error || data.aviso) {
          anunciar(data.error || data.aviso);
          cerrarLista();
          return;
        }
        renderizarSugerencias(data.resultados || []);
      } catch (_) {
        /* Cancelada o sin red */
      }
    }, 300);
  });

  // Navegación completa por teclado (ArrowDown, ArrowUp, Enter, Escape)
  inputDir.addEventListener("keydown", (ev) => {
    if (!sugerenciasActuales.length || listaBox?.classList.contains("hidden")) return;
    const opciones = Array.from(listaBox.querySelectorAll('[role="option"]'));
    if (ev.key === "ArrowDown") {
      ev.preventDefault();
      indiceActivo = (indiceActivo + 1) % opciones.length;
    } else if (ev.key === "ArrowUp") {
      ev.preventDefault();
      indiceActivo = (indiceActivo - 1 + opciones.length) % opciones.length;
    } else if (ev.key === "Enter" && indiceActivo >= 0) {
      ev.preventDefault();
      elegirSugerencia(sugerenciasActuales[indiceActivo]);
      return;
    } else if (ev.key === "Escape") {
      cerrarLista();
      return;
    } else {
      return;
    }
    opciones.forEach((op, idx) => {
      const sel = idx === indiceActivo;
      op.setAttribute("aria-selected", sel ? "true" : "false");
      op.classList.toggle("bg-marino-100", sel);
    });
    inputDir.setAttribute("aria-activedescendant", opciones[indiceActivo].id);
  });

  inputDir.addEventListener("blur", () => setTimeout(cerrarLista, 150));

  async function consultarInversa(lat, lng) {
    try {
      const resp = await fetch(`/api/geo/inversa/?lat=${lat}&lon=${lng}`);
      const data = await resp.json();
      if (data.resultado && data.resultado.direccion && panelConfirmarInv && textoInv) {
        direccionSugeridaInversa = data.resultado.direccion;
        textoInv.textContent = direccionSugeridaInversa;
        panelConfirmarInv.classList.remove("hidden");
      }
    } catch (_) {}
  }

  btnAceptarInv?.addEventListener("click", () => {
    if (direccionSugeridaInversa) {
      inputDir.value = direccionSugeridaInversa;
      if (inputDirNorm) inputDirNorm.value = direccionSugeridaInversa;
      panelConfirmarInv?.classList.add("hidden");
    }
  });

  // Alternativa sin arrastrar: mover pin ~15 m con botones Norte/Sur/Este/Oeste (# Sección 2.4)
  const PASO = 0.00014;
  document.querySelectorAll("[data-mover-pin]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const lat = parseFloat(inputLat.value) || -33.491;
      const lng = parseFloat(inputLng.value) || -70.6745;
      const dir = btn.dataset.moverPin;
      const nLat = dir === "norte" ? lat + PASO : dir === "sur" ? lat - PASO : lat;
      const nLng = dir === "este" ? lng + PASO : dir === "oeste" ? lng - PASO : lng;
      actualizarCoordenadas(nLat, nLng, "MANUAL");
      anunciar(`Pin movido hacia el ${dir}.`);
    });
  });

  // Botón "Usar mi ubicación actual" (útil para fiscalizador en terreno)
  document.getElementById("btn-usar-gps-actual")?.addEventListener("click", () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition((pos) => {
      actualizarCoordenadas(pos.coords.latitude, pos.coords.longitude, "FISCALIZADOR");
      consultarInversa(pos.coords.latitude, pos.coords.longitude);
    });
  });

  // Inicializar mapa pequeño con pin arrastrable
  if (contenedorMapa && soportaWebGL()) {
    fetch("/api/mapa/config/")
      .then((r) => r.json())
      .then((config) => {
        if (!config.tiene_clave_mapa || !config.estilo_url) {
          contenedorMapa.innerHTML =
            '<div class="p-4 text-sm font-semibold text-marino-900 bg-ambar-100 rounded-xl">Mapa visual no configurado aún; usa los botones de ajuste o las coordenadas manuales.</div>';
          return;
        }
        const latIni = parseFloat(inputLat.value) || config.centroide.lat;
        const lngIni = parseFloat(inputLng.value) || config.centroide.lng;
        const { mapa, maplibregl } = crearMapaVectorial({
          container: contenedorMapa,
          config: { ...config, centroide: { lat: latIni, lng: lngIni } },
          embebido: true,
        });
        mapaSel = mapa;
        marcador = new maplibregl.Marker({ draggable: true, color: "#C8401C" })
          .setLngLat([lngIni, latIni])
          .addTo(mapa);

        marcador.on("dragend", () => {
          const p = marcador.getLngLat();
          actualizarCoordenadas(p.lat, p.lng, "MANUAL");
          consultarInversa(p.lat, p.lng);
        });

        mapa.on("click", (ev) => {
          actualizarCoordenadas(ev.lngLat.lat, ev.lngLat.lng, "MANUAL");
          consultarInversa(ev.lngLat.lat, ev.lngLat.lng);
        });
      })
      .catch(() => {});
  }
}

document.addEventListener("DOMContentLoaded", iniciarBuscadorUbicacion);

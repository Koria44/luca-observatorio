/**
 * Escáner de códigos de barras (EAN-13 / EAN-8 / UPC) con la cámara del celular
 * usando la API nativa `BarcodeDetector` + búsqueda rápida manual por código EAN.
 * Selecciona automáticamente el producto en `/precios/registrar/` y `/precios/terreno/`.
 */
(function iniciarEscanerEAN() {
  const btnAbrir = document.getElementById("btn-abrir-escaner-ean");
  const btnCerrar = document.getElementById("btn-cerrar-escaner-ean");
  const panelVideo = document.getElementById("panel-video-ean");
  const video = document.getElementById("video-escaner-ean");
  const inputEan = document.getElementById("input-codigo-ean");
  const btnBuscarEan = document.getElementById("btn-buscar-ean");
  const estadoEan = document.getElementById("estado-escaner-ean");
  const selectProducto = document.getElementById("id_producto");

  if (!inputEan || !selectProducto) return;

  let streamActivo = null;
  let intervaloDeteccion = null;

  function detenerCamara() {
    if (intervaloDeteccion) clearInterval(intervaloDeteccion);
    if (streamActivo) {
      streamActivo.getTracks().forEach((t) => t.stop());
      streamActivo = null;
    }
    panelVideo?.classList.add("hidden");
  }

  async function buscarPorCodigo(codigo) {
    const limpio = String(codigo || "").replace(/\D/g, "");
    if (limpio.length < 8) {
      if (estadoEan) estadoEan.textContent = "Ingresa un código de barras válido (8 a 14 dígitos).";
      return;
    }
    if (estadoEan) estadoEan.textContent = `Buscando código ${limpio}…`;
    try {
      const resp = await fetch(`/catalogo/api/ean/${encodeURIComponent(limpio)}/`);
      const data = await resp.json();
      if (resp.ok && data.encontrado) {
        selectProducto.value = String(data.producto.id);
        selectProducto.dispatchEvent(new Event("change"));
        if (estadoEan) estadoEan.textContent = `✔ Producto seleccionado: ${data.producto.nombre_completo}`;
        detenerCamara();
      } else {
        if (estadoEan) estadoEan.textContent = `✘ No encontramos un producto con código ${limpio} en el catálogo.`;
      }
    } catch (_) {
      if (estadoEan) estadoEan.textContent = "Error al consultar el catálogo.";
    }
  }

  btnBuscarEan?.addEventListener("click", () => buscarPorCodigo(inputEan.value));
  inputEan.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      buscarPorCodigo(inputEan.value);
    }
  });

  btnCerrar?.addEventListener("click", detenerCamara);

  btnAbrir?.addEventListener("click", async () => {
    if (!("BarcodeDetector" in window)) {
      if (estadoEan) {
        estadoEan.textContent =
          "Tu navegador no soporta escaneo automático por cámara; escribe o pega el código EAN abajo y presiona Buscar.";
      }
      inputEan.focus();
      return;
    }

    try {
      streamActivo = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
        audio: false,
      });
      if (video) {
        video.srcObject = streamActivo;
        await video.play();
      }
      panelVideo?.classList.remove("hidden");
      if (estadoEan) estadoEan.textContent = "Apunta la cámara al código de barras del envase…";

      const detector = new window.BarcodeDetector({ formats: ["ean_13", "ean_8", "upc_a", "upc_e"] });
      intervaloDeteccion = setInterval(async () => {
        if (!video || video.readyState < 2) return;
        try {
          const codigos = await detector.detect(video);
          if (codigos.length > 0 && codigos[0].rawValue) {
            inputEan.value = codigos[0].rawValue;
            buscarPorCodigo(codigos[0].rawValue);
          }
        } catch (_) {}
      }, 400);
    } catch (_) {
      if (estadoEan) estadoEan.textContent = "No se pudo abrir la cámara. Puedes ingresar el código EAN manualmente.";
    }
  });
})();

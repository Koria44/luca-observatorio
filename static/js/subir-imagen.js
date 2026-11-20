/**
 * Compresión previa en navegador y vista previa accesible para subida de fotos/logos
 * (# REQ-11, REQ-12 / Prompt 5 Sección 3.2).
 *
 * Reduce el archivo a máx. 1600 px y calidad ~0.8 antes de enviarlo al servidor
 * (cuidando el límite de 4 MB / Vercel). Si el navegador no puede decodificar el formato
 * (p. ej. HEIC), muestra un mensaje amable pidiendo JPG o PNG.
 */
(function iniciarSubidaImagen() {
  document.querySelectorAll("[data-subir-imagen]").forEach((input) => {
    const preview = document.getElementById(input.dataset.previewId || "preview-imagen");
    const aviso = document.getElementById(input.dataset.avisoId || "aviso-imagen");

    input.addEventListener("change", async () => {
      const archivo = input.files?.[0];
      if (!archivo) return;

      if (aviso) aviso.textContent = "Procesando y optimizando imagen…";

      try {
        const bitmap = await createImageBitmap(archivo);
        const maxLado = 1600;
        let ancho = bitmap.width;
        let alto = bitmap.height;
        if (ancho > maxLado || alto > maxLado) {
          const factor = maxLado / Math.max(ancho, alto);
          ancho = Math.round(ancho * factor);
          alto = Math.round(alto * factor);
        }

        const canvas = document.createElement("canvas");
        canvas.width = ancho;
        canvas.height = alto;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(bitmap, 0, 0, ancho, alto);

        const tipoSalida = archivo.type === "image/png" ? "image/png" : "image/jpeg";
        const blob = await new Promise((resolve) => canvas.toBlob(resolve, tipoSalida, 0.8));
        if (blob && blob.size <= 4 * 1024 * 1024) {
          const nuevoNombre = archivo.name.replace(/\.[^.]+$/, "") + (tipoSalida === "image/png" ? ".png" : ".jpg");
          const dt = new DataTransfer();
          dt.items.add(new File([blob], nuevoNombre, { type: tipoSalida }));
          input.files = dt.files;

          if (preview) {
            preview.src = URL.createObjectURL(blob);
            preview.classList.remove("hidden");
          }
          if (aviso) {
            aviso.textContent = `✔ Imagen lista (${Math.round(blob.size / 1024)} KB, ${ancho}×${alto} px).`;
          }
        } else if (aviso) {
          aviso.textContent = "✘ La imagen sigue superando 4 MB. Prueba con una foto más pequeña.";
        }
      } catch (_) {
        if (aviso) {
          aviso.textContent = "⚠ No pudimos leer este formato en tu navegador (por ejemplo HEIC). Por favor elige una foto JPG o PNG.";
        }
      }
    });
  });
})();

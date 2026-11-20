/**
 * Gestión privada de Mi Lista de Compras / Canasta Personal (100 % en base de datos por usuario).
 * Compara producto por producto y permite alternar escenarios de 1, 2, 3 locales o Ahorro máximo.
 * # SEGURIDAD: Todo texto dinámico proveniente de nombres de productos/locales se escapa contra XSS.
 */

function obtenerCsrf() {
  const partes = document.cookie.split(";").map((c) => c.trim());
  for (const p of partes) {
    if (p.startsWith("csrftoken=")) return decodeURIComponent(p.slice(10));
  }
  return "";
}

function escaparHtml(texto) {
  return String(texto ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatoCLP(v) {
  return `$${Number(v || 0).toLocaleString("es-CL")}`;
}

function actualizarContadorBadge(total) {
  document.querySelectorAll("[data-canasta-contador]").forEach((el) => {
    el.textContent = total > 0 ? String(total) : "";
    el.classList.toggle("hidden", total === 0);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  // Botones "+ Mi lista" en el buscador, comparador y ofertas (solo rol VECINO)
  document.querySelectorAll("[data-agregar-canasta]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const pid = Number(btn.dataset.productoId);
      if (!pid) return;
      try {
        const resp = await fetch("/api/canasta/agregar/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": obtenerCsrf(),
            "X-Requested-With": "XMLHttpRequest",
          },
          body: JSON.stringify({ producto_id: pid }),
        });
        if (!resp.ok) return;
        const data = await resp.json();
        actualizarContadorBadge(data.total_items || 0);
        const txtOrig = btn.textContent;
        btn.textContent = "✔ En mi lista";
        setTimeout(() => {
          btn.textContent = txtOrig;
        }, 1500);
      } catch (_) {}
    });
  });

  // Página privada `/mi-canasta/`
  const contenedor = document.getElementById("app-mi-canasta");
  if (!contenedor) return;

  const imgLucasPulgar = contenedor.dataset.lucasPulgar || "/static/img/marca/mascota-lucas-pulgar.svg";
  const imgLucasBuscando = contenedor.dataset.lucasBuscando || "/static/img/marca/mascota-lucas-buscando.svg";

  let items = [];
  let ultimoResultado = null;
  let escenarioActivoId = null;

  try {
    items = JSON.parse(contenedor.dataset.itemsIniciales || "[]");
  } catch (_) {
    items = [];
  }

  const listaEl = document.getElementById("lista-items-canasta");
  const resultadoEl = document.getElementById("resultado-optimizacion-canasta");
  const btnWhatsapp = document.getElementById("btn-compartir-canasta-wa");
  const selUmbral = document.getElementById("sel-umbral-desvio");
  const selMaxLocales = document.getElementById("sel-max-locales");

  async function recalcular() {
    renderizarItems();
    actualizarContadorBadge(items.reduce((acc, it) => acc + (Number(it.cantidad) || 1), 0));

    const umbral = Number(selUmbral?.value ?? 500);
    const maxLocales = Number(selMaxLocales?.value ?? 3);

    if (!items.length) {
      ultimoResultado = null;
      escenarioActivoId = null;
      if (resultadoEl) {
        resultadoEl.innerHTML = `
          <div class="tarjeta-luca text-center space-y-3 py-10">
            <img src="${escaparHtml(imgLucasBuscando)}" alt="Lucas esperando tu lista" class="w-28 mx-auto">
            <h2 class="text-2xl">Tu lista todavía está vacía</h2>
            <p class="text-sm text-pizarra-600 max-w-md mx-auto">Agrega productos desde las sugerencias o el buscador y te muestro en qué locales conviene comprar cada uno.</p>
          </div>
        `;
      }
      btnWhatsapp?.classList.add("hidden");
      await fetch("/api/canasta/calcular/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": obtenerCsrf(),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ items: [], umbral_desvio: umbral, max_locales: maxLocales }),
      }).catch(() => {});
      return;
    }

    try {
      const resp = await fetch("/api/canasta/calcular/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": obtenerCsrf(),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ items, umbral_desvio: umbral, max_locales: maxLocales }),
      });
      const data = await resp.json();
      ultimoResultado = data;
      escenarioActivoId = data.escenario_recomendado_id || (data.escenarios?.[0]?.id ?? null);
      renderizarResultado();
    } catch (_) {
      if (resultadoEl) {
        resultadoEl.innerHTML = '<div class="tarjeta-luca text-rojo-600 font-bold">No se pudo calcular la canasta en este momento.</div>';
      }
    }
  }

  function renderizarItems() {
    if (!listaEl) return;
    if (!items.length) {
      listaEl.innerHTML = '<li class="text-sm text-pizarra-600 bg-crema-50 rounded-2xl p-4 text-center">No hay productos agregados todavía.</li>';
      return;
    }
    listaEl.innerHTML = "";
    items.forEach((it, idx) => {
      const li = document.createElement("li");
      li.className = "flex flex-wrap items-center justify-between gap-2 bg-crema-50/70 rounded-2xl px-4 py-2.5 border border-crema-200";
      li.innerHTML = `
        <span class="font-bold text-tinta-900">${escaparHtml(it.nombre)}</span>
        <div class="flex items-center gap-1.5">
          <button type="button" data-menos="${idx}" class="w-9 h-9 rounded-full bg-white border border-crema-200 hover:border-tinta-900 font-bold transition-colors" aria-label="Restar cantidad">−</button>
          <span class="font-titulo font-extrabold min-w-[26px] text-center tabular-nums">${Number(it.cantidad) || 1}</span>
          <button type="button" data-mas="${idx}" class="w-9 h-9 rounded-full bg-white border border-crema-200 hover:border-tinta-900 font-bold transition-colors" aria-label="Sumar cantidad">+</button>
          <button type="button" data-quitar="${idx}" class="px-3 py-1.5 rounded-full bg-tomate-100 text-tomate-600 hover:bg-tomate-600 hover:text-white font-bold text-xs transition-colors">Quitar</button>
        </div>
      `;
      listaEl.appendChild(li);
    });

    listaEl.querySelectorAll("[data-menos]").forEach((b) =>
      b.addEventListener("click", () => {
        const i = Number(b.dataset.menos);
        if (items[i].cantidad > 1) items[i].cantidad -= 1;
        else items.splice(i, 1);
        recalcular();
      })
    );
    listaEl.querySelectorAll("[data-mas]").forEach((b) =>
      b.addEventListener("click", () => {
        const i = Number(b.dataset.mas);
        items[i].cantidad = Math.min(20, items[i].cantidad + 1);
        recalcular();
      })
    );
    listaEl.querySelectorAll("[data-quitar]").forEach((b) =>
      b.addEventListener("click", () => {
        items.splice(Number(b.dataset.quitar), 1);
        recalcular();
      })
    );
  }

  function actualizarEnlaceWhatsapp(escenario) {
    if (!btnWhatsapp || !escenario || !escenario.locales?.length) {
      btnWhatsapp?.classList.add("hidden");
      return;
    }
    const bloques = escenario.locales.map((loc) => {
      const lineas = loc.items.map((it) => `  - ${it.cantidad}x ${it.producto}: ${formatoCLP(it.subtotal)}`).join("\n");
      return `*${loc.nombre}* (${loc.sector}) — Subtotal ${formatoCLP(loc.subtotal_clp)}:\n${lineas}`;
    });
    const texto =
      `Mi ruta de compras en Luca (Pedro Aguirre Cerda):\n` +
      `Total (${escenario.paradas} ${escenario.paradas === 1 ? "local" : "locales"}): ${formatoCLP(escenario.total_clp)}` +
      (escenario.ahorro_vs_uno > 0 ? ` · Ahorras ${formatoCLP(escenario.ahorro_vs_uno)} vs 1 solo local` : "") +
      `\n\n${bloques.join("\n\n")}`;
    btnWhatsapp.href = `https://wa.me/?text=${encodeURIComponent(texto)}`;
    btnWhatsapp.classList.remove("hidden");
  }

  function renderizarResultado() {
    if (!resultadoEl || !ultimoResultado) return;
    const escenarios = ultimoResultado.escenarios || [];
    const analisis = ultimoResultado.analisis_productos || [];
    const sinPrecio = ultimoResultado.sin_precio || [];

    if (!escenarios.length) {
      resultadoEl.innerHTML = `
        <div class="tarjeta-luca text-center space-y-3 py-8">
          <img src="${escaparHtml(imgLucasBuscando)}" alt="Sin precios vigentes" class="w-24 mx-auto">
          <p class="font-bold text-tinta-900">No encontramos precios vigentes para esos productos.</p>
          ${sinPrecio.length ? `<a href="${escaparHtml(sinPrecio[0].url_alerta)}" class="btn-acento !py-2 !px-4 text-sm">Crear alerta de precio</a>` : ""}
        </div>
      `;
      btnWhatsapp?.classList.add("hidden");
      return;
    }

    const activo = escenarios.find((e) => e.id === escenarioActivoId) || escenarios[0];
    actualizarEnlaceWhatsapp(activo);

    // 1. Resumen superior de la ruta seleccionada
    const textoParadas = activo.paradas === 1 ? "1 local" : `${activo.paradas} locales`;
    let html = `
      <div class="rounded-tarjeta bg-tinte-menta border-2 border-ahorro-600 p-5 sm:p-6 shadow-luca space-y-3">
        <div class="flex items-start justify-between gap-3">
          <div class="space-y-1">
            <span class="cinta-mejor-precio">${activo.recomendado ? "★ Ruta recomendada" : "Ruta seleccionada"} · ${escaparHtml(textoParadas)}</span>
            <p class="text-4xl precio-destacado text-ahorro-700 pt-1">${formatoCLP(activo.total_clp)}</p>
            <p class="text-sm text-tinta-900 font-semibold">
              Cubre ${activo.cubiertos} de ${activo.total_solicitados} productos
              ${activo.ahorro_vs_uno > 0 ? ` · <strong class="text-ahorro-700">Ahorras ${formatoCLP(activo.ahorro_vs_uno)}</strong> frente a comprar todo en 1 solo local` : ""}
            </p>
          </div>
          <img src="${escaparHtml(imgLucasPulgar)}" alt="Lucas celebrando tu ahorro" class="w-16 h-16 shrink-0 hidden sm:block">
        </div>

        <!-- Selector de escenarios -->
        <div class="flex flex-wrap gap-2 pt-2 border-t border-ahorro-600/20" role="tablist" aria-label="Escenarios de ruta">
          ${escenarios
            .map((e) => {
              const sel = e.id === activo.id;
              return `
                <button type="button" data-escenario="${escaparHtml(e.id)}" role="tab" aria-selected="${sel ? "true" : "false"}"
                  class="px-3.5 py-2 rounded-2xl text-left text-xs font-titulo font-bold border-2 transition-all ${
                    sel
                      ? "bg-tinta-900 text-white border-tinta-900 shadow-sm"
                      : "bg-white text-tinta-900 border-crema-200 hover:border-ahorro-600"
                  }">
                  <div class="flex items-center gap-1.5">
                    <span>${escaparHtml(e.titulo)}</span>
                    ${e.recomendado ? '<span class="px-1.5 py-0.5 rounded-full bg-luca-400 text-tinta-900 text-[10px]">★</span>' : ""}
                  </div>
                  <div class="text-sm precio-destacado mt-0.5">${formatoCLP(e.total_clp)}${
                    e.ahorro_vs_uno > 0 ? ` <span class="${sel ? "text-luca-400" : "text-ahorro-700"}">(−${formatoCLP(e.ahorro_vs_uno)})</span>` : ""
                  }</div>
                </button>
              `;
            })
            .join("")}
        </div>
      </div>
    `;

    // 2. Tarjetas por local: qué productos comprar en cada uno
    html += `<div class="space-y-4">`;
    activo.locales.forEach((loc, idx) => {
      html += `
        <article class="tarjeta-luca space-y-3">
          <div class="flex flex-wrap items-start justify-between gap-2 pb-3 border-b border-crema-200">
            <div class="space-y-0.5">
              <div class="flex flex-wrap items-center gap-2">
                <span class="px-2.5 py-0.5 rounded-full bg-tinte-cielo text-tinta-900 text-xs font-titulo font-extrabold">Parada ${idx + 1}</span>
                <span class="text-xs font-bold text-pizarra-600">${escaparHtml(loc.sector)}</span>
              </div>
              <h3 class="text-xl"><a href="${escaparHtml(loc.url)}" class="hover:text-ahorro-600 transition-colors">${escaparHtml(loc.nombre)}</a></h3>
              <p class="text-xs text-pizarra-600">${escaparHtml(loc.direccion)}</p>
            </div>
            <div class="text-left sm:text-right">
              <p class="text-xs font-bold uppercase text-pizarra-600">Subtotal local</p>
              <p class="text-2xl precio-destacado text-ahorro-600">${formatoCLP(loc.subtotal_clp)}</p>
              <a href="${escaparHtml(loc.maps_url)}" target="_blank" rel="noopener noreferrer" class="text-xs font-bold text-tinta-700 underline">Cómo llegar ↗</a>
            </div>
          </div>

          <ul class="space-y-2">
            ${loc.items
              .map((it) => {
                const badgeMejor = it.es_mejor_global
                  ? `<span class="px-2 py-0.5 rounded-full bg-ahorro-100 text-ahorro-700 text-[11px] font-bold">★ Más barato aquí${
                      it.ahorro_vs_caro > 0 ? ` · ahorras ${formatoCLP(it.ahorro_vs_caro)}` : ""
                    }</span>`
                  : it.mejor_otro_local
                  ? `<span class="px-2 py-0.5 rounded-full bg-luca-100 text-tinta-900 text-[11px] font-bold">ℹ ${formatoCLP(
                      it.mejor_otro_local.diferencia_subtotal
                    )} más barato en ${escaparHtml(it.mejor_otro_local.local)}</span>`
                  : "";
                const badgeOferta = it.es_oferta
                  ? `<span class="px-2 py-0.5 rounded-full bg-tomate-100 text-tomate-600 text-[11px] font-bold">Oferta</span>`
                  : "";
                const badgeCond = (it.condiciones || [])
                  .map((c) => `<span class="px-2 py-0.5 rounded-full bg-crema-100 text-tinta-900 text-[11px] font-semibold">⚠ ${escaparHtml(c)}</span>`)
                  .join(" ");
                return `
                  <li class="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-crema-50/70 px-3.5 py-2.5 border border-crema-200/80">
                    <div class="space-y-1">
                      <p class="font-bold text-tinta-900 text-sm">${Number(it.cantidad)}× ${escaparHtml(it.producto)}</p>
                      <div class="flex flex-wrap gap-1.5">${badgeMejor} ${badgeOferta} ${badgeCond}</div>
                    </div>
                    <div class="text-right shrink-0">
                      <p class="font-titulo font-extrabold text-tinta-900 tabular-nums">${formatoCLP(it.subtotal)}</p>
                      <p class="text-[11px] text-pizarra-600 tabular-nums">${formatoCLP(it.precio_unitario)} c/u</p>
                    </div>
                  </li>
                `;
              })
              .join("")}
          </ul>
        </article>
      `;
    });
    html += `</div>`;

    // 3. Avisos de productos sin precio o faltantes en esta ruta
    if (sinPrecio.length) {
      html += `
        <div class="tarjeta-luca border-l-4 border-tomate-600 bg-tomate-100/40 space-y-2">
          <h3 class="text-lg text-tomate-600">Productos sin precio registrado hoy (${sinPrecio.length})</h3>
          <ul class="space-y-1.5 text-sm">
            ${sinPrecio
              .map(
                (sp) => `
              <li class="flex flex-wrap items-center justify-between gap-2">
                <span class="font-bold text-tinta-900">${escaparHtml(sp.nombre)}</span>
                <a href="${escaparHtml(sp.url_alerta)}" class="btn-acento !py-1 !px-3 text-xs">Crear alerta de precio</a>
              </li>`
              )
              .join("")}
          </ul>
        </div>
      `;
    }

    // 4. Tabla comparativa producto por producto (siempre disponible)
    const disponibles = analisis.filter((a) => a.disponible);
    if (disponibles.length) {
      html += `
        <details class="tarjeta-luca" open>
          <summary class="font-titulo font-extrabold text-lg text-tinta-900 cursor-pointer">Comparativa producto por producto (${disponibles.length})</summary>
          <div class="overflow-x-auto mt-3">
            <table class="w-full text-left text-xs sm:text-sm border-collapse">
              <thead>
                <tr class="border-b-2 border-tinta-900 text-tinta-900">
                  <th class="py-2 pr-3">Producto</th>
                  <th class="py-2 pr-3">Local más barato</th>
                  <th class="py-2 pr-3">2.ª opción</th>
                  <th class="py-2">Ahorro vs. más caro</th>
                </tr>
              </thead>
              <tbody>
                ${disponibles
                  .map((a) => {
                    const seg = a.segunda_opcion
                      ? `${escaparHtml(a.segunda_opcion.local)} (${formatoCLP(a.segunda_opcion.subtotal)} · +${formatoCLP(
                          a.segunda_opcion.diferencia_subtotal
                        )})`
                      : "Solo 1 local";
                    return `
                      <tr class="border-b border-crema-200">
                        <td class="py-2 pr-3 font-bold text-tinta-900"><a href="${escaparHtml(a.url_comparar)}" class="underline hover:text-ahorro-600">${Number(
                      a.cantidad
                    )}× ${escaparHtml(a.nombre)}</a></td>
                        <td class="py-2 pr-3"><strong class="text-ahorro-700 tabular-nums">${formatoCLP(a.mejor.subtotal)}</strong><br><span class="text-xs text-pizarra-600">${escaparHtml(
                      a.mejor.local
                    )}</span></td>
                        <td class="py-2 pr-3 text-pizarra-600">${seg}</td>
                        <td class="py-2 font-bold text-ahorro-700 tabular-nums">${
                          a.ahorro_vs_caro > 0 ? `−${formatoCLP(a.ahorro_vs_caro)}` : "$0"
                        }</td>
                      </tr>
                    `;
                  })
                  .join("")}
              </tbody>
            </table>
          </div>
        </details>
      `;
    }

    resultadoEl.innerHTML = html;

    resultadoEl.querySelectorAll("[data-escenario]").forEach((btn) => {
      btn.addEventListener("click", () => {
        escenarioActivoId = btn.dataset.escenario;
        renderizarResultado();
      });
    });
  }

  document.querySelectorAll("[data-agregar-rapido]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = Number(btn.dataset.productoId);
      const nombre = btn.dataset.productoNombre;
      if (!items.some((x) => x.producto_id === pid)) {
        items.push({ producto_id: pid, nombre, cantidad: 1 });
        recalcular();
      }
    });
  });

  document.getElementById("btn-vaciar-canasta")?.addEventListener("click", () => {
    items = [];
    recalcular();
  });

  selUmbral?.addEventListener("change", recalcular);
  selMaxLocales?.addEventListener("change", recalcular);

  recalcular();
});

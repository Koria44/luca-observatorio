/**
 * Componentes interactivos accesibles de Luca (# Sección 4 y 6 / WAI-ARIA APG):
 * - Toasts accesibles (6 s con barra de tiempo, pausa en hover/foco, role status/alert).
 * - Modales y menú móvil con focus trap, cierre con Esc y retorno de foco.
 * - Acordeones accesibles (grid-template-rows, aria-expanded/aria-controls).
 * - Pestañas con navegación por teclado (flechas izquierda/derecha, Home/End).
 * - Integración progresiva con @formkit/auto-animate vendorizado en `[data-auto-animar]`.
 */
(function iniciarUILuca() {
  const sinMovimiento = () =>
    window.LucaMovimiento
      ? window.LucaMovimiento.prefiereMenosMovimiento()
      : window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function escapar(txt) {
    return String(txt ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // 1. Toasts accesibles
  function asegurarContenedorToast() {
    let cont = document.getElementById("luca-toasts");
    if (!cont) {
      cont = document.createElement("div");
      cont.id = "luca-toasts";
      cont.className =
        "fixed top-4 right-4 sm:top-auto sm:bottom-5 sm:right-5 z-50 flex flex-col gap-2.5 max-w-sm w-[calc(100vw-2rem)] pointer-events-none";
      document.body.appendChild(cont);
    }
    return cont;
  }

  function mostrarToast(mensaje, tipo = "info") {
    const cont = asegurarContenedorToast();
    const esError = tipo === "error";
    const toast = document.createElement("div");
    toast.setAttribute("role", esError ? "alert" : "status");
    toast.setAttribute("aria-live", esError ? "assertive" : "polite");
    const estilos =
      tipo === "exito"
        ? "bg-white border-l-4 border-ahorro-600 text-tinta-900"
        : esError
        ? "bg-white border-l-4 border-rojo-600 text-rojo-600"
        : "bg-white border-l-4 border-tinta-700 text-tinta-900";
    toast.className = `pointer-events-auto rounded-2xl shadow-nivel-3 px-4 py-3 flex items-start justify-between gap-3 font-semibold text-sm ${estilos} ${
      sinMovimiento() ? "" : "animate-escalar"
    }`;
    toast.innerHTML = `
      <span>${escapar(mensaje)}</span>
      <button type="button" class="min-h-[32px] min-w-[32px] rounded-full hover:bg-crema-100 font-bold text-xs shrink-0" aria-label="Cerrar aviso">✕</button>
    `;
    cont.appendChild(toast);

    let pausado = false;
    let restante = 6000;
    let inicio = Date.now();
    let timer = null;

    const cerrar = () => {
      clearTimeout(timer);
      toast.remove();
    };
    const iniciarTimer = () => {
      inicio = Date.now();
      timer = setTimeout(cerrar, restante);
    };

    toast.querySelector("button")?.addEventListener("click", cerrar);
    toast.addEventListener("mouseenter", () => {
      pausado = true;
      restante -= Date.now() - inicio;
      clearTimeout(timer);
    });
    toast.addEventListener("mouseleave", () => {
      if (pausado) {
        pausado = false;
        iniciarTimer();
      }
    });
    toast.addEventListener("focusin", () => clearTimeout(timer));
    toast.addEventListener("focusout", iniciarTimer);
    iniciarTimer();
  }

  // 2. Focus trap reutilizable para modales
  function activarModal(modal, disparador) {
    const focablesSel = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    modal.classList.remove("hidden");
    const focables = Array.from(modal.querySelectorAll(focablesSel));
    if (focables.length) focables[0].focus();

    const onKey = (ev) => {
      if (ev.key === "Escape") {
        cerrar();
      } else if (ev.key === "Tab" && focables.length) {
        const primero = focables[0];
        const ultimo = focables[focables.length - 1];
        if (ev.shiftKey && document.activeElement === primero) {
          ev.preventDefault();
          ultimo.focus();
        } else if (!ev.shiftKey && document.activeElement === ultimo) {
          ev.preventDefault();
          primero.focus();
        }
      }
    };

    const cerrar = () => {
      modal.classList.add("hidden");
      document.removeEventListener("keydown", onKey);
      if (disparador && typeof disparador.focus === "function") disparador.focus();
    };

    document.addEventListener("keydown", onKey);
    modal.querySelectorAll("[data-cerrar-modal]").forEach((b) => {
      b.onclick = cerrar;
    });
    modal.addEventListener(
      "click",
      (ev) => {
        if (ev.target === modal) cerrar();
      },
      { once: true }
    );
  }

  // 3. Acordeones accesibles
  function iniciarAcordeones() {
    document.querySelectorAll("[data-acordeon-btn]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const abierto = btn.getAttribute("aria-expanded") === "true";
        btn.setAttribute("aria-expanded", abierto ? "false" : "true");
      });
    });
  }

  // 4. Pestañas con teclado (flechas)
  function iniciarPestanas() {
    document.querySelectorAll('[role="tablist"]').forEach((lista) => {
      lista.addEventListener("keydown", (ev) => {
        const tabs = Array.from(lista.querySelectorAll('[role="tab"]'));
        const actual = tabs.indexOf(document.activeElement);
        if (actual === -1) return;
        let siguiente = actual;
        if (ev.key === "ArrowRight") siguiente = (actual + 1) % tabs.length;
        else if (ev.key === "ArrowLeft") siguiente = (actual - 1 + tabs.length) % tabs.length;
        else if (ev.key === "Home") siguiente = 0;
        else if (ev.key === "End") siguiente = tabs.length - 1;
        else return;
        ev.preventDefault();
        tabs[siguiente].focus();
        tabs[siguiente].click();
      });
    });
  }

  // 5. Formulario progresivo por pasos (`[data-pasos-form]`)
  function iniciarPasosFormulario() {
    const form = document.querySelector("[data-pasos-form]");
    if (!form) return;
    const pasos = Array.from(form.querySelectorAll("[data-paso]"));
    const indicadores = Array.from(document.querySelectorAll("[data-indicador-paso]"));
    const controles = form.querySelector("[data-pasos-controles]");
    const btnAnt = form.querySelector("[data-paso-anterior]");
    const btnSig = form.querySelector("[data-paso-siguiente]");
    const btnEnviar = form.querySelector("[data-paso-enviar]");
    if (pasos.length < 2 || !controles) return;

    // Si el servidor devolvió errores, ir al primer paso que contenga error
    let actual = pasos.findIndex((p) => p.querySelector('[role="alert"], .text-rojo-600'));
    if (actual < 0) actual = 0;

    controles.classList.remove("hidden");
    controles.classList.add("flex");

    const render = () => {
      pasos.forEach((p, i) => {
        p.classList.toggle("hidden", i !== actual);
        if (i === actual && !sinMovimiento()) {
          p.classList.remove("animate-aparecer");
          void p.offsetWidth;
          p.classList.add("animate-aparecer");
        }
      });
      indicadores.forEach((ind, i) => {
        const activo = i === actual;
        const listo = i < actual;
        ind.className = `rounded-full py-2 px-2 transition-colors ${
          activo
            ? "bg-ahorro-600 text-white"
            : listo
            ? "bg-ahorro-100 text-ahorro-700"
            : "bg-crema-100 text-pizarra-600"
        }`;
      });
      btnAnt?.classList.toggle("hidden", actual === 0);
      btnSig?.classList.toggle("hidden", actual === pasos.length - 1);
      btnEnviar?.classList.toggle("hidden", actual !== pasos.length - 1);
    };

    btnAnt?.addEventListener("click", () => {
      if (actual > 0) {
        actual -= 1;
        render();
      }
    });
    btnSig?.addEventListener("click", () => {
      if (actual < pasos.length - 1) {
        actual += 1;
        render();
      }
    });
    render();
  }

  // 6. Auto-animate vendorizado para listas `[data-auto-animar]`
  async function iniciarAutoAnimate() {
    const contenedores = document.querySelectorAll("[data-auto-animar]");
    if (!contenedores.length || sinMovimiento()) return;
    try {
      const mod = await import("/static/vendor/auto-animate/index.mjs");
      const autoAnimate = mod.default;
      if (typeof autoAnimate === "function") {
        contenedores.forEach((el) => autoAnimate(el, { duration: 220, easing: "ease-out" }));
      }
    } catch (_) {
      /* mejora progresiva: sin auto-animate la lista funciona igual */
    }
  }

  function iniciar() {
    iniciarAcordeones();
    iniciarPestanas();
    iniciarPasosFormulario();
    iniciarAutoAnimate();

    document.querySelectorAll("[data-abrir-modal]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const modal = document.getElementById(btn.dataset.abrirModal);
        if (modal) activarModal(modal, btn);
      });
    });

    document.querySelectorAll("[data-demo-toast]").forEach((btn) => {
      btn.addEventListener("click", () => {
        mostrarToast(btn.dataset.demoToast, btn.dataset.demoToastTipo || "info");
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }

  window.LucaUI = { mostrarToast, activarModal };
})();

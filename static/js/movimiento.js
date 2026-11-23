/**
 * Gestión centralizada de preferencias de movimiento reducido (# ADR-006 / REQ-12).
 * Combina dos niveles:
 *   1. `prefers-reduced-motion: reduce` del sistema operativo.
 *   2. Interruptor manual "Reducir animaciones" (`data-reducir-animaciones="true"` en <html>).
 * Expone `window.LucaMovimiento.prefiereMenosMovimiento()` y `suscribir(fn)`.
 */
(function iniciarMovimiento() {
  const html = document.documentElement;
  const mq = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  const suscriptores = new Set();

  function leerManual() {
    try {
      return localStorage.getItem("luca_reducir_animaciones") === "1";
    } catch (_) {
      return false;
    }
  }

  function prefiereMenosMovimiento() {
    return Boolean((mq && mq.matches) || html.getAttribute("data-reducir-animaciones") === "true");
  }

  function notificar() {
    const reducido = prefiereMenosMovimiento();
    suscriptores.forEach((fn) => {
      try {
        fn(reducido);
      } catch (_) {}
    });
  }

  function aplicarManual(activo) {
    if (activo) {
      html.setAttribute("data-reducir-animaciones", "true");
      html.classList.add("reducir-animaciones");
    } else {
      html.removeAttribute("data-reducir-animaciones");
      html.classList.remove("reducir-animaciones");
    }
    try {
      localStorage.setItem("luca_reducir_animaciones", activo ? "1" : "0");
    } catch (_) {}

    document.querySelectorAll("#btn-reducir-animaciones, [data-toggle-movimiento]").forEach((btn) => {
      btn.setAttribute("aria-pressed", activo ? "true" : "false");
      if (btn.id === "btn-reducir-animaciones") {
        btn.textContent = activo ? "Animaciones: OFF" : "Reducir animaciones";
      }
    });
    notificar();
  }

  // Restaurar estado al instante
  aplicarManual(leerManual());

  if (mq && typeof mq.addEventListener === "function") {
    mq.addEventListener("change", notificar);
  }

  function conectarBotones() {
    aplicarManual(leerManual());
    document.querySelectorAll("#btn-reducir-animaciones, [data-toggle-movimiento]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const actual = html.getAttribute("data-reducir-animaciones") === "true";
        aplicarManual(!actual);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", conectarBotones);
  } else {
    conectarBotones();
  }

  window.LucaMovimiento = {
    prefiereMenosMovimiento,
    aplicarManual,
    suscribir(fn) {
      suscriptores.add(fn);
      return () => suscriptores.delete(fn);
    },
  };
})();

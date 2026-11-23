/**
 * Animaciones con propósito y presupuesto estricto (# Sección 1 / 6 / ADR-006):
 * - revelar(): IntersectionObserver una sola vez (umbral 0,15), escalonado máx. 60 ms / 8 ítems.
 * - contadores(): 0 → valor en <= 900 ms con tabular-nums; valor directo con movimiento reducido.
 * - barraEncabezado(): compacta el header al hacer scroll usando requestAnimationFrame + listener pasivo.
 * - imagenesBlurUp(): transición suave de opacidad al completar la carga de imágenes.
 */
(function iniciarAnimacionesLuca() {
  const sinMovimiento = () =>
    window.LucaMovimiento
      ? window.LucaMovimiento.prefiereMenosMovimiento()
      : window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
        document.documentElement.getAttribute("data-reducir-animaciones") === "true";

  function revelar() {
    const nodos = Array.from(document.querySelectorAll(".revelar, [data-animar]"));
    if (!nodos.length) return;

    if (sinMovimiento() || !("IntersectionObserver" in window)) {
      nodos.forEach((el) => el.classList.add("visible"));
      return;
    }

    const obs = new IntersectionObserver(
      (entries) => {
        let idx = 0;
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.style.setProperty("--i", String(Math.min(idx, 7)));
            entry.target.classList.add("visible");
            obs.unobserve(entry.target);
            idx += 1;
          }
        });
      },
      { threshold: 0.12 }
    );

    nodos.forEach((el) => {
      const rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight * 0.92) {
        el.classList.add("visible");
      } else {
        obs.observe(el);
      }
    });
  }

  function contadores() {
    const nodos = Array.from(document.querySelectorAll("[data-contador]"));
    if (!nodos.length) return;

    const animarUno = (el) => {
      const objetivo = Number(String(el.dataset.contador || "0").replace(/[^\d.-]/g, ""));
      const prefijo = el.dataset.prefijo || "";
      const sufijo = el.dataset.sufijo || "";
      if (Number.isNaN(objetivo) || sinMovimiento()) {
        el.textContent = `${prefijo}${objetivo.toLocaleString("es-CL")}${sufijo}`;
        return;
      }
      const duracion = 750;
      const inicio = performance.now();
      const paso = (ahora) => {
        const t = Math.min(1, (ahora - inicio) / duracion);
        const eased = 1 - Math.pow(1 - t, 3);
        const val = Math.round(objetivo * eased);
        el.textContent = `${prefijo}${val.toLocaleString("es-CL")}${sufijo}`;
        if (t < 1) requestAnimationFrame(paso);
      };
      requestAnimationFrame(paso);
    };

    if (sinMovimiento() || !("IntersectionObserver" in window)) {
      nodos.forEach(animarUno);
      return;
    }
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            animarUno(e.target);
            obs.unobserve(e.target);
          }
        });
      },
      { threshold: 0.2 }
    );
    nodos.forEach((el) => obs.observe(el));
  }

  function barraEncabezado() {
    const header = document.querySelector("header[data-encabezado]");
    if (!header) return;
    let pendiente = false;
    const actualizar = () => {
      pendiente = false;
      header.classList.toggle("encabezado-compacto", window.scrollY > 24);
    };
    window.addEventListener(
      "scroll",
      () => {
        if (!pendiente) {
          pendiente = true;
          requestAnimationFrame(actualizar);
        }
      },
      { passive: true }
    );
    actualizar();
  }

  function imagenesBlurUp() {
    document.querySelectorAll("img.img-blur-up").forEach((img) => {
      if (img.complete) {
        img.removeAttribute("data-cargando");
      } else {
        img.setAttribute("data-cargando", "1");
        img.addEventListener("load", () => img.removeAttribute("data-cargando"), { once: true });
        img.addEventListener("error", () => img.removeAttribute("data-cargando"), { once: true });
      }
    });
  }

  function iniciar() {
    revelar();
    contadores();
    barraEncabezado();
    imagenesBlurUp();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();

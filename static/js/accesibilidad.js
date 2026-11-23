/**
 * Barra de preferencias persistente en localStorage (# REQ-12).
 * Controla tamaño de texto (A- / A / A+) y Modo oscuro.
 */
(function iniciarAccesibilidad() {
  const html = document.documentElement;

  function aplicarEscala(valor) {
    const acotado = Math.max(0.85, Math.min(1.35, Number(valor) || 1));
    html.style.setProperty("--escala-texto", String(acotado));
    try {
      localStorage.setItem("luca_escala_texto", String(acotado));
    } catch (_) {
      /* almacenamiento deshabilitado */
    }
  }

  function actualizarBotonOscuro(activo) {
    const btn = document.getElementById("btn-modo-oscuro");
    if (!btn) return;
    btn.setAttribute("aria-pressed", activo ? "true" : "false");
    btn.textContent = activo ? "Modo claro" : "Modo oscuro";
  }

  function restaurarPreferencias() {
    try {
      const escala = parseFloat(localStorage.getItem("luca_escala_texto") || "1");
      if (!Number.isNaN(escala)) aplicarEscala(escala);

      const activo = localStorage.getItem("luca_modo_oscuro") === "1";
      html.classList.toggle("modo-oscuro", activo);
      actualizarBotonOscuro(activo);
    } catch (_) {
      /* sin acceso a localStorage */
    }
  }

  function conectarControles() {
    restaurarPreferencias();

    document.getElementById("btn-texto-menos")?.addEventListener("click", () => {
      const actual = parseFloat(getComputedStyle(html).getPropertyValue("--escala-texto") || "1");
      aplicarEscala(actual - 0.1);
    });

    document.getElementById("btn-texto-normal")?.addEventListener("click", () => aplicarEscala(1));

    document.getElementById("btn-texto-mas")?.addEventListener("click", () => {
      const actual = parseFloat(getComputedStyle(html).getPropertyValue("--escala-texto") || "1");
      aplicarEscala(actual + 0.1);
    });

    document.getElementById("btn-modo-oscuro")?.addEventListener("click", () => {
      const activo = html.classList.toggle("modo-oscuro");
      actualizarBotonOscuro(activo);
      try {
        localStorage.setItem("luca_modo_oscuro", activo ? "1" : "0");
      } catch (_) {}
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", conectarControles);
  } else {
    conectarControles();
  }
})();

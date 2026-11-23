/**
 * Carrusel accesible para banners destacados (# II.9 / REQ-12 / WCAG 2.2.2).
 * Soporta botón Pausa/Reproducir, flechas, puntos, teclado, swipe táctil,
 * pausa al enfocar / cambiar de pestaña y respeto estricto a `LucaMovimiento`.
 */
(function iniciarCarrusel() {
  const carrusel = document.querySelector("[data-carrusel]");
  if (!carrusel) return;

  const slides = Array.from(carrusel.querySelectorAll("[data-slide]"));
  const puntos = Array.from(carrusel.querySelectorAll("[data-punto]"));
  const btnPrev = carrusel.querySelector("[data-prev]");
  const btnNext = carrusel.querySelector("[data-next]");
  const btnPausa = carrusel.querySelector("[data-pausa]");
  if (slides.length <= 1) return;

  const sinMovimiento = () =>
    window.LucaMovimiento
      ? window.LucaMovimiento.prefiereMenosMovimiento()
      : window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
        document.documentElement.getAttribute("data-reducir-animaciones") === "true";

  let indice = 0;
  let pausado = sinMovimiento();
  let touchX = 0;

  function mostrar(nuevo) {
    indice = (nuevo + slides.length) % slides.length;
    slides.forEach((s, i) => {
      s.classList.toggle("hidden", i !== indice);
      s.setAttribute("aria-hidden", i === indice ? "false" : "true");
    });
    puntos.forEach((p, i) => {
      p.setAttribute("aria-current", i === indice ? "true" : "false");
      p.classList.toggle("bg-ahorro-600", i === indice);
      p.classList.toggle("bg-tinta-900/25", i !== indice);
    });
  }

  function actualizarBotonPausa() {
    if (!btnPausa) return;
    const span = btnPausa.querySelector("span");
    if (span) span.textContent = pausado ? "Reproducir" : "Pausar";
    else btnPausa.textContent = pausado ? "Reproducir" : "Pausar";
    btnPausa.setAttribute("aria-pressed", pausado ? "true" : "false");
  }

  btnPrev?.addEventListener("click", () => mostrar(indice - 1));
  btnNext?.addEventListener("click", () => mostrar(indice + 1));
  puntos.forEach((p, i) => p.addEventListener("click", () => mostrar(i)));

  btnPausa?.addEventListener("click", () => {
    pausado = !pausado;
    actualizarBotonPausa();
  });

  carrusel.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowLeft") mostrar(indice - 1);
    if (ev.key === "ArrowRight") mostrar(indice + 1);
  });

  carrusel.addEventListener("focusin", () => {
    pausado = true;
    actualizarBotonPausa();
  });

  carrusel.addEventListener("touchstart", (ev) => {
    touchX = ev.changedTouches[0]?.clientX || 0;
  }, { passive: true });
  carrusel.addEventListener("touchend", (ev) => {
    const dx = (ev.changedTouches[0]?.clientX || 0) - touchX;
    if (Math.abs(dx) > 45) mostrar(dx < 0 ? indice + 1 : indice - 1);
  }, { passive: true });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      pausado = true;
      actualizarBotonPausa();
    }
  });

  if (window.LucaMovimiento) {
    window.LucaMovimiento.suscribir((reducido) => {
      if (reducido) {
        pausado = true;
        actualizarBotonPausa();
      }
    });
  }

  actualizarBotonPausa();
  mostrar(0);

  setInterval(() => {
    if (!pausado && !document.hidden && !sinMovimiento()) mostrar(indice + 1);
  }, 6500);
})();

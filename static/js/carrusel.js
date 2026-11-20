/**
 * Carrusel accesible para banners de productos estrella y ofertas (# II.9 / REQ-12).
 * Soporta botón Pausa/Reproducir, flechas, puntos, teclado (ArrowLeft/ArrowRight),
 * pausa al enfocar y respeto estricto a `prefers-reduced-motion`.
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

  let indice = 0;
  let pausado = window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    document.documentElement.classList.contains("reducir-animaciones");

  function mostrar(nuevo) {
    indice = (nuevo + slides.length) % slides.length;
    slides.forEach((s, i) => {
      s.classList.toggle("hidden", i !== indice);
      s.setAttribute("aria-hidden", i === indice ? "false" : "true");
    });
    puntos.forEach((p, i) => {
      p.setAttribute("aria-current", i === indice ? "true" : "false");
      p.classList.toggle("bg-ambar-400", i === indice);
      p.classList.toggle("bg-white/50", i !== indice);
    });
  }

  function actualizarBotonPausa() {
    if (!btnPausa) return;
    btnPausa.textContent = pausado ? "▶ Reproducir" : "⏸ Pausar";
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

  actualizarBotonPausa();
  mostrar(0);

  setInterval(() => {
    if (!pausado) mostrar(indice + 1);
  }, 6500);
})();

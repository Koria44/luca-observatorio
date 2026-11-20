/**
 * Animaciones sutiles de entrada con IntersectionObserver (# II.9 / REQ-12).
 * El contenido permanece siempre visible (opacity: 1) para evitar secciones ocultas
 * si el navegador demora o en capturas completas; la animación solo agrega un suave
 * desplazamiento vertical al entrar en pantalla.
 */
(function iniciarAnimaciones() {
  const reducir =
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    document.documentElement.classList.contains("reducir-animaciones");
  if (reducir || !("IntersectionObserver" in window)) return;

  const elementos = document.querySelectorAll("[data-animar]");
  if (!elementos.length) return;

  const obs = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.remove("translate-y-3");
          entry.target.classList.add("translate-y-0");
          obs.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.05 }
  );

  elementos.forEach((el) => {
    const rect = el.getBoundingClientRect();
    if (rect.top > window.innerHeight) {
      el.classList.add("transition-transform", "duration-500", "translate-y-3");
      obs.observe(el);
    }
  });
})();

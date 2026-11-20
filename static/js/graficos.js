/**
 * Renderizado accesible de gráficos Chart.js para historial de precios y dashboards (# REQ-06, REQ-07).
 * Paleta A "Almacén de barrio", respeta `prefers-reduced-motion` y formatea valores en pesos chilenos (CLP).
 */
(function iniciarGraficosLuca() {
  if (typeof window.Chart === "undefined") return;
  const sinAnimacion =
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    document.documentElement.classList.contains("reducir-animaciones");

  const PALETA_BARRAS = [
    "#0E7A55",
    "#1B2A4A",
    "#FFC53D",
    "#C2410C",
    "#283E6B",
    "#14966A",
    "#D99200",
    "#EA580C",
  ];

  document.querySelectorAll("canvas[data-grafico-historial]").forEach((canvas) => {
    const datos = JSON.parse(canvas.dataset.graficoHistorial || "[]");
    if (!datos.length) return;
    new window.Chart(canvas, {
      type: "line",
      data: {
        labels: datos.map((d) => d.fecha),
        datasets: [
          {
            label: "Precio promedio (CLP)",
            data: datos.map((d) => d.promedio),
            borderColor: "#1B2A4A",
            backgroundColor: "rgba(27, 42, 74, 0.10)",
            borderWidth: 3,
            pointRadius: 4,
            pointBackgroundColor: "#1B2A4A",
            tension: 0.3,
            fill: true,
          },
          {
            label: "Precio más bajo (CLP)",
            data: datos.map((d) => d.minimo),
            borderColor: "#0E7A55",
            backgroundColor: "rgba(14, 122, 85, 0.12)",
            borderWidth: 3,
            pointRadius: 4,
            pointBackgroundColor: "#0E7A55",
            borderDash: [6, 4],
            tension: 0.3,
          },
        ],
      },
      options: {
        responsive: true,
        animation: sinAnimacion ? false : { duration: 600 },
        scales: {
          y: {
            ticks: {
              callback: (v) => `$${Number(v).toLocaleString("es-CL")}`,
            },
          },
        },
      },
    });
  });

  document.querySelectorAll("canvas[data-grafico-barras]").forEach((canvas) => {
    const datos = JSON.parse(canvas.dataset.graficoBarras || "[]");
    if (!datos.length) return;
    const colores = datos.map((_, i) => PALETA_BARRAS[i % PALETA_BARRAS.length]);
    new window.Chart(canvas, {
      type: "bar",
      data: {
        labels: datos.map((d) => d.etiqueta),
        datasets: [
          {
            label: canvas.dataset.tituloSerie || "Valor (CLP)",
            data: datos.map((d) => d.valor),
            backgroundColor: colores,
            borderColor: "#1B2A4A",
            borderWidth: 1,
            borderRadius: 10,
          },
        ],
      },
      options: {
        responsive: true,
        animation: sinAnimacion ? false : { duration: 600 },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: (v) =>
                canvas.dataset.esMoneda === "1"
                  ? `$${Number(v).toLocaleString("es-CL")}`
                  : Number(v).toLocaleString("es-CL"),
            },
          },
        },
      },
    });
  });
})();

/**
 * Configuración de Tailwind CSS 3.4 para Luca (Observatorio de Precios · Pedro Aguirre Cerda).
 * # ADR-006: Escalas 50–900, roles semánticos (WCAG 2.1 AA >= 4,5:1), tipografía autoalojada,
 * sombras con tinte marino en 4 niveles, sistema de movimiento y variante `sin-anim`.
 */
const plugin = require("tailwindcss/plugin");

module.exports = {
  content: [
    "./templates/**/*.html",
    "./apps/**/templates/**/*.html",
    "./apps/**/*.py",
    "./static/js/**/*.js",
    "./static/img/marca/guia-de-marca.html",
  ],
  safelist: [
    "bg-marino-700",
    "bg-turquesa-700",
    "bg-coral-600",
    "bg-verde-700",
    "bg-azul-600",
    "animate-aparecer",
    "animate-subir",
    "animate-escalar",
    "animate-destello-precio",
    "animate-caer-pin",
  ],
  theme: {
    extend: {
      colors: {
        // Escalas completas 50–900 de la paleta de marca (# Sección 3.1)
        marino: {
          50: "#EEF3FA",
          100: "#E4EDFF",
          200: "#C5D7F2",
          300: "#97B7E4",
          400: "#638FD0",
          500: "#3D6CB5",
          600: "#2D528E",
          700: "#243B64",
          800: "#1F3256",
          900: "#1B2A4A",
        },
        azul: {
          50: "#EFF6FF",
          100: "#E4EDFF",
          200: "#BFDBFE",
          300: "#93C5FD",
          400: "#60A5FA",
          500: "#3B82F6",
          600: "#283E6B",
          700: "#1D4ED8",
          800: "#1E40AF",
          900: "#1E3A8A",
        },
        turquesa: {
          50: "#ECFDF7",
          100: "#DDF5EA",
          200: "#B4E8D2",
          300: "#7DD5B3",
          400: "#42B88E",
          500: "#0E7A55",
          600: "#0C6E4D",
          700: "#0B6B4B",
          800: "#09543B",
          900: "#07422E",
        },
        ambar: {
          50: "#FFFBEB",
          100: "#FFF1C2",
          200: "#FDE28A",
          300: "#FCD34D",
          400: "#FFC53D",
          500: "#C47D00",
          600: "#A66600",
          700: "#854D0E",
          800: "#713F12",
          900: "#542E0B",
        },
        coral: {
          50: "#FFF4ED",
          100: "#FFE6D5",
          200: "#FEC8A6",
          300: "#FDA16E",
          400: "#FB7B3C",
          500: "#EA580C",
          600: "#C2410C",
          700: "#9A3412",
          800: "#7C2D12",
          900: "#5C210D",
        },
        verde: {
          50: "#ECFDF5",
          100: "#DDF5EA",
          200: "#A7F3D0",
          300: "#6EE7B7",
          400: "#34D399",
          500: "#14966A",
          600: "#0E7A55",
          700: "#0B6B4B",
          800: "#065F46",
          900: "#064E3B",
        },
        rojo: {
          50: "#FEF2F2",
          100: "#FEE2E2",
          200: "#FECACA",
          300: "#FCA5A5",
          400: "#F87171",
          500: "#EF4444",
          600: "#B91C1C",
          700: "#991B1B",
          800: "#7F1D1D",
          900: "#63171B",
        },
        crema: {
          50: "#FFF8EC",
          100: "#F5EAD6",
          200: "#EADBC0",
          300: "#DEC8A3",
          400: "#CCA978",
          500: "#B28B55",
          600: "#8F6D3F",
          700: "#6E532F",
          800: "#523D22",
          900: "#382A17",
        },
        gris: {
          50: "#FAF8F4",
          100: "#F5EFE3",
          200: "#E5DFD3",
          300: "#CBD5E1",
          400: "#94A3B8",
          500: "#64748B",
          600: "#4A5568",
          700: "#4A5568",
          800: "#28354D",
          900: "#1B2A4A",
        },

        // Roles semánticos "Almacén de barrio"
        tinta: { 900: "#1B2A4A", 700: "#283E6B", 100: "#E4EDFF" },
        ahorro: { 700: "#0B6B4B", 600: "#0E7A55", 500: "#14966A", 100: "#DDF5EA" },
        luca: { 500: "#C47D00", 400: "#FFC53D", 100: "#FFF1C2" },
        tomate: { 600: "#C2410C", 500: "#EA580C", 100: "#FFE6D5" },
        pizarra: { 900: "#1B2A4A", 700: "#334155", 600: "#4A5568", 500: "#64748B", 200: "#E5DFD3", 100: "#F5EFE3" },
        tinte: {
          menta: "#DDF5EA",
          durazno: "#FFE6D5",
          cielo: "#E4EDFF",
          mantequilla: "#FFF1C2",
          lavanda: "#EDE9FE",
        },
      },
      fontFamily: {
        sans: ['"Atkinson Hyperlegible"', "system-ui", "-apple-system", "sans-serif"],
        titulo: ['"Baloo 2"', '"Atkinson Hyperlegible"', "system-ui", "sans-serif"],
      },
      fontSize: {
        "fluido-hero": ["clamp(1.85rem, 3.8vw, 3.1rem)", { lineHeight: "1.12" }],
        "fluido-h1": ["clamp(1.65rem, 2.8vw, 2.35rem)", { lineHeight: "1.18" }],
        "fluido-h2": ["clamp(1.3rem, 2vw, 1.75rem)", { lineHeight: "1.24" }],
      },
      borderRadius: {
        sm: "0.75rem", // 12px
        md: "1rem",    // 16px
        tarjeta: "1.5rem", // 24px
      },
      boxShadow: {
        // 4 niveles de sombra suave con tinte marino (# Sección 3.1)
        "nivel-1": "0 2px 8px -2px rgba(27, 42, 74, 0.10), 0 1px 3px -1px rgba(27, 42, 74, 0.06)",
        "nivel-2": "0 10px 28px -14px rgba(27, 42, 74, 0.22), 0 2px 6px -2px rgba(27, 42, 74, 0.08)",
        "nivel-3": "0 18px 36px -14px rgba(27, 42, 74, 0.28), 0 4px 10px -2px rgba(27, 42, 74, 0.10)",
        "nivel-4": "0 24px 48px -16px rgba(27, 42, 74, 0.34), 0 8px 18px -6px rgba(27, 42, 74, 0.14)",
        "luca-suave": "0 4px 16px -8px rgba(27, 42, 74, 0.14)",
        luca: "0 10px 28px -14px rgba(27, 42, 74, 0.22), 0 2px 6px -2px rgba(27, 42, 74, 0.08)",
        "luca-hover": "0 18px 36px -14px rgba(27, 42, 74, 0.28), 0 4px 10px -2px rgba(27, 42, 74, 0.10)",
      },
      minHeight: {
        tactil: "3rem", // 48px mínimo táctil WCAG / adultos mayores
      },
      minWidth: {
        tactil: "3rem",
      },
      // Sistema de movimiento controlado (# Sección 3.2)
      transitionTimingFunction: {
        "salida-suave": "cubic-bezier(0.22, 1, 0.36, 1)",
        "entrada-suave": "cubic-bezier(0.64, 0, 0.78, 0)",
        resorte: "cubic-bezier(0.34, 1.56, 0.64, 1)",
      },
      keyframes: {
        aparecer: { from: { opacity: "0" }, to: { opacity: "1" } },
        subir: {
          from: { opacity: "0", transform: "translateY(16px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        escalar: {
          from: { opacity: "0", transform: "scale(0.96)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        brillo: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        flotar: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        "pulso-suave": {
          "0%": { boxShadow: "0 0 0 0 rgb(255 197 61 / 0.45)" },
          "70%, 100%": { boxShadow: "0 0 0 12px rgb(255 197 61 / 0)" },
        },
        dibujar: { to: { strokeDashoffset: "0" } },
        "caer-pin": {
          "0%": { opacity: "0", transform: "translateY(-20px)" },
          "70%": { opacity: "1", transform: "translateY(2px)" },
          "100%": { transform: "translateY(0)" },
        },
        "destello-precio": {
          "0%": { backgroundColor: "rgb(255 244 214)" },
          "100%": { backgroundColor: "transparent" },
        },
      },
      animation: {
        aparecer: "aparecer 0.4s ease-out both",
        subir: "subir 0.55s cubic-bezier(0.22, 1, 0.36, 1) both",
        escalar: "escalar 0.25s cubic-bezier(0.22, 1, 0.36, 1) both",
        brillo: "brillo 1.6s linear infinite",
        flotar: "flotar 5s ease-in-out infinite",
        "pulso-suave": "pulso-suave 2s ease-out 3",
        dibujar: "dibujar 0.55s ease-out forwards",
        "caer-pin": "caer-pin 0.45s cubic-bezier(0.22, 1, 0.36, 1) both",
        "destello-precio": "destello-precio 1.2s ease-out",
      },
    },
  },
  plugins: [
    require("tailwindcss-animate"),
    require("@tailwindcss/forms")({ strategy: "class" }),
    plugin(({ addVariant }) => {
      // Variante para el interruptor "Reducir animaciones" de la barra de accesibilidad (# REQ-12)
      addVariant("sin-anim", 'html[data-reducir-animaciones="true"] &');
    }),
  ],
};

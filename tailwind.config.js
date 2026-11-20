/**
 * Configuración de Tailwind CSS 3.4 para Luca (Observatorio de Precios · PAC).
 * Paleta A "Almacén de barrio": psicología del color 60-30-10 con contraste WCAG 2.1 AA (>= 4,5:1).
 * Tipografía amigable y legible para personas mayores (Atkinson Hyperlegible + Baloo 2 / Nunito).
 */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./apps/**/templates/**/*.html",
    "./apps/**/*.py",
    "./static/js/**/*.js",
    "./static/img/marca/guia-de-marca.html",
  ],
  theme: {
    extend: {
      colors: {
        // Tokens semánticos principales — Paleta A "Almacén de barrio"
        tinta: {
          900: "#1B2A4A",
          700: "#283E6B",
          100: "#E4EDFF",
        },
        ahorro: {
          700: "#0B6B4B",
          600: "#0E7A55",
          500: "#14966A",
          100: "#DDF5EA",
        },
        luca: {
          500: "#C47D00",
          400: "#FFC53D",
          100: "#FFF1C2",
        },
        tomate: {
          600: "#C2410C",
          500: "#EA580C",
          100: "#FFE6D5",
        },
        crema: {
          50: "#FFF8EC",
          100: "#F5EAD6",
          200: "#EADBC0",
        },
        pizarra: {
          900: "#1B2A4A",
          700: "#334155",
          600: "#4A5568",
          500: "#64748B",
          200: "#E5DFD3",
          100: "#F5EFE3",
        },
        // Tintes suaves de categoría (contraste >= 11,8:1 con tinta-900)
        tinte: {
          menta: "#DDF5EA",
          durazno: "#FFE6D5",
          cielo: "#E4EDFF",
          mantequilla: "#FFF1C2",
          lavanda: "#EDE9FE",
        },

        // Alias armonizados con Paleta A para compatibilidad total con vistas existentes
        marino: {
          900: "#1B2A4A",
          700: "#243B64",
          100: "#E4EDFF",
        },
        azul: {
          600: "#283E6B",
          100: "#E4EDFF",
        },
        turquesa: {
          700: "#0B6B4B",
          500: "#0E7A55",
          100: "#DDF5EA",
        },
        ambar: {
          500: "#C47D00",
          400: "#FFC53D",
          100: "#FFF1C2",
        },
        coral: {
          600: "#C2410C",
          500: "#EA580C",
          100: "#FFE6D5",
        },
        verde: {
          700: "#0B6B4B",
          600: "#0E7A55",
          100: "#DDF5EA",
        },
        rojo: {
          600: "#B91C1C",
          100: "#FEE2E2",
        },
        gris: {
          900: "#1B2A4A",
          700: "#4A5568",
          500: "#64748B",
          200: "#E5DFD3",
          100: "#F5EFE3",
        },
      },
      fontFamily: {
        sans: ['"Atkinson Hyperlegible"', "system-ui", "-apple-system", "sans-serif"],
        titulo: ['"Baloo 2"', '"Nunito"', '"Atkinson Hyperlegible"', "system-ui", "sans-serif"],
      },
      borderRadius: {
        tarjeta: "1.5rem",
      },
      boxShadow: {
        luca: "0 10px 28px -14px rgba(27, 42, 74, 0.22), 0 2px 6px -2px rgba(27, 42, 74, 0.08)",
        "luca-hover": "0 18px 36px -14px rgba(27, 42, 74, 0.28), 0 4px 10px -2px rgba(27, 42, 74, 0.10)",
        "luca-suave": "0 4px 16px -8px rgba(27, 42, 74, 0.14)",
      },
      minHeight: {
        tactil: "3rem", // 48px mínimo táctil WCAG / adultos mayores
      },
      minWidth: {
        tactil: "3rem",
      },
    },
  },
  plugins: [],
};

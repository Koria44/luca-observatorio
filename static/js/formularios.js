/**
 * Mejora progresiva de formularios accesibles (validación en vivo, formateo de RUT,
 * sugerencia de correo, medidor de fortaleza de contraseña y botón mostrar/ocultar).
 * # II.6 / REQ-12
 */
import {
  evaluarFortalezaPassword,
  formatearRut,
  validarCorreo,
  validarRut,
  validarTelefonoCl,
} from "./validadores.js";

function asegurarMensajeCampo(input) {
  const idMsg = `${input.id || input.name}-feedback`;
  let el = document.getElementById(idMsg);
  if (!el) {
    el = document.createElement("p");
    el.id = idMsg;
    el.setAttribute("aria-live", "polite");
    el.className = "mt-1.5 text-sm font-semibold";
    input.insertAdjacentElement("afterend", el);
  }
  return el;
}

document.addEventListener("DOMContentLoaded", () => {
  // Validación en vivo de campos con atributo `data-validar`
  document.querySelectorAll("[data-validar]").forEach((input) => {
    const tipo = input.dataset.validar;

    if (tipo === "rut") {
      input.addEventListener("input", () => {
        if (input.value.length >= 2) {
          input.value = formatearRut(input.value);
        }
      });
      input.addEventListener("blur", () => {
        if (!input.value.trim()) return;
        const res = validarRut(input.value);
        const msg = asegurarMensajeCampo(input);
        msg.textContent = res.valido ? `✔ ${res.mensaje}` : `✘ ${res.mensaje}`;
        msg.className = `mt-1.5 text-sm font-semibold ${res.valido ? "text-verde-700" : "text-rojo-600"}`;
        input.setAttribute("aria-invalid", res.valido ? "false" : "true");
      });
    }

    if (tipo === "telefono") {
      input.addEventListener("blur", () => {
        if (!input.value.trim()) return;
        const res = validarTelefonoCl(input.value);
        const msg = asegurarMensajeCampo(input);
        msg.textContent = res.valido ? `✔ ${res.mensaje} (${res.normalizado})` : `✘ ${res.mensaje}`;
        msg.className = `mt-1.5 text-sm font-semibold ${res.valido ? "text-verde-700" : "text-rojo-600"}`;
        input.setAttribute("aria-invalid", res.valido ? "false" : "true");
      });
    }

    if (tipo === "correo") {
      input.addEventListener("blur", () => {
        if (!input.value.trim()) return;
        const res = validarCorreo(input.value);
        const msg = asegurarMensajeCampo(input);
        if (!res.valido) {
          msg.textContent = `✘ ${res.mensaje}`;
          msg.className = "mt-1.5 text-sm font-semibold text-rojo-600";
        } else if (res.sugerencia) {
          msg.textContent = `⚠ ${res.mensaje}`;
          msg.className = "mt-1.5 text-sm font-semibold text-marino-900 bg-ambar-100 px-3 py-1 rounded-lg";
        } else {
          msg.textContent = `✔ ${res.mensaje}`;
          msg.className = "mt-1.5 text-sm font-semibold text-verde-700";
        }
        input.setAttribute("aria-invalid", res.valido ? "false" : "true");
      });
    }

    if (tipo === "password") {
      input.addEventListener("input", () => {
        const res = evaluarFortalezaPassword(input.value);
        const msg = asegurarMensajeCampo(input);
        msg.textContent = `Seguridad de contraseña: ${res.nivel}`;
        msg.className = `mt-1.5 text-sm font-bold ${res.color}`;
      });
    }
  });

  // Botones accesibles para mostrar/ocultar contraseña
  document.querySelectorAll("[data-toggle-password]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.dataset.togglePassword;
      const input = document.getElementById(targetId);
      if (!input) return;
      const esPassword = input.type === "password";
      input.type = esPassword ? "text" : "password";
      btn.textContent = esPassword ? "Ocultar" : "Mostrar";
      btn.setAttribute("aria-pressed", esPassword ? "true" : "false");
    });
  });
});

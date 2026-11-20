/**
 * Validadores chilenos de cliente (RUT, teléfono, correo y fortaleza de contraseña).
 * Replican exactamente las mismas reglas de `apps/nucleo/validadores.py` para
 * ofrecer retroalimentación inmediata y accesible (# II.6 / REQ-12).
 *
 * # SEGURIDAD: Esta validación es solo comodidad visual; el servidor siempre revalida.
 */

export const DOMINIOS_SUGERIDOS = {
  "gmial.com": "gmail.com",
  "gamil.com": "gmail.com",
  "gnail.com": "gmail.com",
  "gmail.cl": "gmail.com",
  "gmail.con": "gmail.com",
  "hotmial.com": "hotmail.com",
  "hotmal.com": "hotmail.com",
  "hotmail.con": "hotmail.com",
  "outlok.com": "outlook.com",
  "outllok.com": "outlook.com",
  "yaho.com": "yahoo.com",
  "yahoo.con": "yahoo.com",
};

export function calcularDvRut(cuerpo) {
  let suma = 0;
  let mult = 2;
  for (let i = cuerpo.length - 1; i >= 0; i -= 1) {
    suma += parseInt(cuerpo[i], 10) * mult;
    mult = mult === 7 ? 2 : mult + 1;
  }
  const resto = 11 - (suma % 11);
  if (resto === 11) return "0";
  if (resto === 10) return "K";
  return String(resto);
}

export function formatearRut(valor) {
  const limpio = String(valor || "").replace(/[\s.\-]/g, "").toUpperCase();
  if (limpio.length < 2) return limpio;
  const cuerpo = limpio.slice(0, -1).replace(/\D/g, "");
  const dv = limpio.slice(-1);
  if (!cuerpo) return limpio;
  const cuerpoConPuntos = cuerpo.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${cuerpoConPuntos}-${dv}`;
}

export function validarRut(valor) {
  const limpio = String(valor || "").replace(/[\s.\-]/g, "").toUpperCase();
  if (!limpio) {
    return { valido: false, mensaje: "Ingresa tu RUT (ejemplo: 12.345.678-5)." };
  }
  if (limpio.length < 8 || limpio.length > 9) {
    return {
      valido: false,
      mensaje: "El RUT debe tener entre 7 y 8 números más su dígito verificador.",
    };
  }
  const cuerpo = limpio.slice(0, -1);
  const dv = limpio.slice(-1);
  if (!/^\d+$/.test(cuerpo) || !/^[0-9K]$/.test(dv)) {
    return {
      valido: false,
      mensaje: "El RUT solo puede contener números y la letra K al final.",
    };
  }
  if (parseInt(cuerpo, 10) < 1000000 || /^0+$/.test(cuerpo)) {
    return { valido: false, mensaje: "El RUT ingresado no es válido." };
  }
  if (calcularDvRut(cuerpo) !== dv) {
    return {
      valido: false,
      mensaje: "El dígito verificador del RUT no coincide. Revísalo por favor.",
    };
  }
  return {
    valido: true,
    normalizado: `${parseInt(cuerpo, 10)}-${dv}`,
    formateado: formatearRut(`${parseInt(cuerpo, 10)}${dv}`),
    mensaje: "RUT válido.",
  };
}

export function validarTelefonoCl(valor) {
  const crudo = String(valor || "").trim();
  if (!crudo) {
    return {
      valido: false,
      mensaje: "Ingresa un teléfono chileno válido (ejemplo: +56 9 1234 5678).",
    };
  }
  if (/[A-Za-z]/.test(crudo)) {
    return { valido: false, mensaje: "El teléfono no debe contener letras." };
  }
  let digitos = crudo.replace(/\D/g, "");
  if (digitos.startsWith("56") && digitos.length === 11) {
    digitos = digitos.slice(2);
  } else if (digitos.startsWith("0") && digitos.length === 10) {
    digitos = digitos.slice(1);
  }
  if (digitos.length !== 9) {
    return {
      valido: false,
      mensaje: "El teléfono chileno debe tener 9 dígitos (celular 9… o fijo RM 2…).",
    };
  }
  if (digitos[0] !== "9" && digitos[0] !== "2") {
    return {
      valido: false,
      mensaje: "Ingresa un celular chileno (empieza con 9) o fijo de Santiago (empieza con 2).",
    };
  }
  return {
    valido: true,
    normalizado: `+56${digitos}`,
    mensaje: "Teléfono válido.",
  };
}

export function validarCorreo(valor) {
  const limpio = String(valor || "").trim().toLowerCase();
  if (!limpio) {
    return { valido: false, mensaje: "Ingresa un correo electrónico válido." };
  }
  if (/\s/.test(limpio) || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(limpio)) {
    return {
      valido: false,
      mensaje: "El correo electrónico no tiene un formato válido (ejemplo: nombre@correo.cl).",
    };
  }
  const [usuario, dominio] = limpio.split("@");
  const sugerido = DOMINIOS_SUGERIDOS[dominio]
    ? `${usuario}@${DOMINIOS_SUGERIDOS[dominio]}`
    : null;
  return {
    valido: true,
    normalizado: limpio,
    sugerencia: sugerido,
    mensaje: sugerido ? `¿Quisiste decir ${sugerido}?` : "Correo válido.",
  };
}

export function evaluarFortalezaPassword(valor) {
  const s = String(valor || "");
  let puntos = 0;
  if (s.length >= 10) puntos += 2;
  else if (s.length >= 6) puntos += 1;
  if (/[A-Z]/.test(s) && /[a-z]/.test(s)) puntos += 1;
  if (/\d/.test(s)) puntos += 1;
  if (/[^A-Za-z0-9]/.test(s)) puntos += 1;

  if (s.length < 10 || puntos <= 2) {
    return { nivel: "Débil", color: "text-rojo-600", porcentaje: 33 };
  }
  if (puntos <= 4) {
    return { nivel: "Aceptable", color: "text-ambar-500", porcentaje: 68 };
  }
  return { nivel: "Fuerte", color: "text-verde-700", porcentaje: 100 };
}

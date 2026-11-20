/**
 * Control de latido (heartbeat) y aviso accesible de inactividad (# II.7 / ADR-003).
 *
 * Mientras el usuario autenticado mantiene la pestaña abierta, envía `POST /cuenta/latido/`
 * cada 60 segundos. Dos minutos antes de cumplirse el límite de inactividad muestra
 * un modal accesible ("¿Sigue ahí? Su sesión se cerrará pronto") con botón grande
 * "Seguir conectado".
 */
(function iniciarControlSesion() {
  const cuerpo = document.body;
  if (!cuerpo || cuerpo.dataset.autenticado !== "1") return;

  const urlLatido = cuerpo.dataset.urlLatido || "/cuenta/latido/";
  const limiteSeg = parseInt(cuerpo.dataset.limiteInactividad || "1800", 10);
  const avisoAntesSeg = 120; // 2 minutos antes

  let ultimoMovimiento = Date.now();
  let modalMostrado = false;

  const modal = document.getElementById("modal-sesion-inactiva");
  const btnSeguir = document.getElementById("btn-seguir-conectado");

  function obtenerCookie(nombre) {
    const partes = document.cookie.split(";").map((c) => c.trim());
    for (const p of partes) {
      if (p.startsWith(`${nombre}=`)) {
        return decodeURIComponent(p.slice(nombre.length + 1));
      }
    }
    return "";
  }

  async function enviarLatido(renovarActividad = false) {
    try {
      const formData = new FormData();
      if (renovarActividad) formData.append("renovar_actividad", "1");
      const resp = await fetch(urlLatido, {
        method: "POST",
        headers: {
          "X-CSRFToken": obtenerCookie("csrftoken"),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: formData,
        credentials: "same-origin",
      });
      if (resp.status === 401) {
        window.location.href = "/cuenta/ingresar/";
      }
    } catch (_) {
      /* Red temporalmente no disponible */
    }
  }

  function registrarActividad() {
    if (!modalMostrado) {
      ultimoMovimiento = Date.now();
    }
  }

  ["click", "keydown", "touchstart", "scroll"].forEach((ev) => {
    window.addEventListener(ev, registrarActividad, { passive: true });
  });

  // Latido periódico cada 60 segundos
  setInterval(() => enviarLatido(false), 60000);

  // Revisión de inactividad cada 10 segundos
  setInterval(() => {
    const inactivoSeg = (Date.now() - ultimoMovimiento) / 1000;
    if (inactivoSeg >= limiteSeg) {
      window.location.href = "/cuenta/ingresar/";
      return;
    }
    if (inactivoSeg >= Math.max(60, limiteSeg - avisoAntesSeg) && !modalMostrado && modal) {
      modalMostrado = true;
      modal.classList.remove("hidden");
      btnSeguir?.focus();
    }
  }, 10000);

  btnSeguir?.addEventListener("click", async () => {
    modalMostrado = false;
    ultimoMovimiento = Date.now();
    modal?.classList.add("hidden");
    await enviarLatido(true);
  });
})();

#!/usr/bin/env python3
"""
Control de seguridad para el agente que responde por Telegram (hook PreToolUse).
Revisa cada herramienta ANTES de ejecutarla y devuelve allow o deny.

Protege contra instrucciones escondidas en correos, páginas o documentos:
secretos, envíos en nombre de el usuario, compras, borrados y cambios al propio control.
Es una barrera por patrones: reduce el riesgo, pero no lo elimina.
Ante cualquier error decide deny (falla cerrado).
"""

import json
import os
import re
import sys
from datetime import datetime
from urllib.parse import urlparse
try:
    from scripts.user_config import USER_NAME, ASSISTANT_NAME
except ImportError:  # ejecución directa: python3 scripts/<archivo>.py
    from user_config import USER_NAME, ASSISTANT_NAME

AUDIT_LOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "memoria", "agent_tool_audit.log",
)

# Rutas que el agente no debe tocar: secretos y el propio mecanismo de control.
PROTECTED = [
    (r"\.env\b", "archivo de secretos"),
    (r"\.ssh\b|\.aws\b|\.netrc\b|\.pem\b|id_rsa|id_ed25519", "credenciales"),
    (r"oauth-token|jetski-standalone|\bkeychain", "credenciales"),
    (r"login data|\bcookies\b", "datos de sesión del navegador"),
    (r"\.agents\b|hooks\.json|agent_safety_gate|antigravity_bridge\.py|env_loader\.py", "control de seguridad"),
    (r"launchagents|\.zshrc|\.zprofile|\.bash_profile|\.gemini/config", "configuración del sistema"),
]

# Comandos de terminal no permitidos.
SHELL_DENY = [
    (r"(^|[\s;|&(`])(curl|wget|nc|ncat|netcat|telnet|ftp|sftp|scp|ssh|rsync)\s", "salida de red no controlada"),
    (r"(^|[\s;|&(`])(sudo|su|launchctl|crontab|security|diskutil|csrutil|spctl|systemsetup)\s", "cambio de sistema"),
    (r"defaults\s+write|\bchmod\b|\bchown\b|\bmkfs\b|\bdd\s+if=", "cambio de sistema"),
    (r"\brm\s+-[a-z]*[rf]|\bgit\s+(push|remote)\b|\bshred\b|\bsrm\b", "borrado o publicación"),
    (r"(pip3?|npm|pnpm|yarn|brew|gem)\s+(install|add|i)\b|\bnpx\s", "instalación de software"),
    (r"base64\s+(-d|-D|--decode)|\beval\s|\bxxd\b", "comando ofuscado"),
    (r"(python3?|node|ruby|perl)\s+-[a-z]*\s.*(requests|urllib|socket|http|fetch)", "red desde código en línea"),
    (r"<<.*(requests|urllib|socket|http\.client)", "red desde código en línea"),
    (r"outgoing message|\bsend\b.*\bmail\b|tell application \"mail\".*\b(send|delete|move)\b", "envío o borrado de correo"),
    (r"osascript.*(do shell script|keystroke|do javascript|system events)", "automatización peligrosa"),
]

# Herramientas MCP con efectos irreversibles o hacia terceros.
TOOL_NAME_DENY = re.compile(
    r"(send|reply|forward|delete|remove|trash|purge|share|publish|invite|"
    r"purchase|checkout|payment|transfer|evaluate|puppeteer_fill|system_run)",
    re.IGNORECASE,
)

# Servidores externos que el bot puede usar. Los que ejecutan código quedan fuera.
MCP_ALLOWED_SERVERS = {
    "notion", "canva", "pptx", "2slides", "slidev", "microsoft-365",
    "google-chrome", "brave-browser", "linear",
}

# Sitios donde el navegador con sesiones abiertas puede operar.
BROWSER_ALLOWED_HOSTS = (
    "mercadolibre.cl", "notion.so", "notion.com",
    "canva.com", "docs.google.com", "drive.google.com", "calendar.google.com",
)

BROWSER_CLICK_DENY = re.compile(
    r"comprar|pagar|pago|confirmar|enviar|eliminar|borrar|checkout|buy|pay\b|submit|delete",
    re.IGNORECASE,
)


def host_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in BROWSER_ALLOWED_HOSTS)


def evaluate(name: str, args: dict):
    """Devuelve (permitido, motivo)."""
    blob = json.dumps(args, ensure_ascii=False).lower()

    # Las herramientas externas llegan como call_mcp_tool: se evalúa la herramienta real.
    if name == "call_mcp_tool":
        if str(args.get("ServerName", "")).lower() not in MCP_ALLOWED_SERVERS:
            return False, "servidor externo no habilitado para el bot"
        name = str(args.get("ToolName", ""))
        inner = args.get("Arguments") or {}
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except ValueError:
                inner = {"raw": inner}
        args = inner if isinstance(inner, dict) else {"raw": inner}

    name_lower = name.lower()

    for pattern, label in PROTECTED:
        if re.search(pattern, blob):
            return False, f"protegido: {label}"

    if TOOL_NAME_DENY.search(name):
        return False, "acción irreversible o hacia terceros"

    command = args.get("CommandLine") or args.get("command")
    if isinstance(command, str):
        lowered = " ".join(command.lower().split())
        for pattern, label in SHELL_DENY:
            if re.search(pattern, lowered, re.DOTALL):
                return False, f"comando bloqueado: {label}"

    if "puppeteer_navigate" in name_lower and not host_allowed(str(args.get("url", ""))):
        return False, "sitio fuera de la lista permitida para el navegador con sesiones"

    if "puppeteer_click" in name_lower and BROWSER_CLICK_DENY.search(blob):
        return False, "clic en una acción sensible"

    return True, ""


def audit(name: str, allowed: bool, reason: str) -> None:
    # Solo nombre y decisión: los argumentos pueden contener datos personales.
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            verdict = "ALLOW" if allowed else "DENY"
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {verdict} {name} {reason}\n")
    except OSError:
        pass


def main() -> None:
    try:
        call = json.load(sys.stdin)["toolCall"]
        name, args = call["name"], call.get("args") or {}
        allowed, reason = evaluate(name, args)
    except Exception:
        name, allowed, reason = "desconocida", False, "no se pudo validar la herramienta"

    audit(name if name != "call_mcp_tool" else f"{name} keys={sorted(args)}", allowed, reason)
    if allowed:
        print(json.dumps({"decision": "allow"}))
    else:
        print(json.dumps({
            "decision": "deny",
            "reason": (
                f"Bloqueado por seguridad ({reason}). No lo intentes por otra vía. "
                f"Dile a {USER_NAME} qué se bloqueó y que puede hacerlo él directamente."
            ),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()

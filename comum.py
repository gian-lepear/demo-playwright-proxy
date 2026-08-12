"""Peças compartilhadas pelos quatro scripts.

`encodedDataLength` do CDP é byte real na rede, já comprimido, e é a única
grandeza do lado cliente comparável com o que um proxy fatura. Somar
`len(response.body())` mediria o conteúdo descomprimido e infla o número.
"""

import re
import socket
import subprocess
import time
from dataclasses import dataclass, field

from playwright.sync_api import CDPSession

ALVO = "https://books.toscrape.com/"

PROXY_HOST = "localhost"
PROXY_PORTA = 3128
PROXY_USUARIO = "demo"
PROXY_SENHA = "demo123"

PROXY = {
    "server": f"http://{PROXY_HOST}:{PROXY_PORTA}",
    "username": PROXY_USUARIO,
    "password": PROXY_SENHA,
}

# Minúsculo é o vocabulário do `route` do Playwright.
BLOQUEADOS_ROUTE = {"image", "stylesheet", "font", "media"}

# Capitalizado é o do CDP, e é OUTRO conjunto de strings. Copiar o set de cima
# para o handler CDP dá um filtro que nunca casa, sem erro nenhum: a página
# carrega inteira e parece que o bloqueio funcionou.
BLOQUEADOS_CDP = {"Image", "Stylesheet", "Font", "Media"}

# O Squid só escreve a linha do CONNECT quando o túnel fecha, e o túnel fecha no
# `browser.close()`. Ler o log na hora pega o túnel da execução anterior.
ESPERA_LOG_SQUID = 2.0


@dataclass
class Medicao:
    rotulo: str
    requisicoes: int = 0
    bytes_rede: int = 0
    bloqueadas: int = 0
    por_tipo: dict[str, int] = field(default_factory=dict)

    @property
    def kib(self) -> float:
        return self.bytes_rede / 1024


def exigir_proxy() -> None:
    """Aborta antes de medir se o proxy não estiver no ar.

    Sem isto o script segue adiante e imprime a explicação de sempre, que passa
    a ser mentira: o erro na tela vira `ERR_PROXY_CONNECTION_FAILED` e a
    narração continua falando de 407 e de timeout.
    """
    try:
        socket.create_connection((PROXY_HOST, PROXY_PORTA), timeout=3).close()
    except OSError:
        raise SystemExit(
            f"proxy fora do ar em {PROXY_HOST}:{PROXY_PORTA}, rode `just up`"
        ) from None


def contar_bytes(cdp: CDPSession, medicao: Medicao) -> None:
    """Liga o contador de bytes numa sessão CDP já criada.

    `Network.enable` é obrigatório para receber `loadingFinished`. Convive com
    `Fetch.enable`, que é outro domínio do protocolo.
    """
    cdp.send("Network.enable")

    tipos: dict[str, str] = {}

    def ao_responder(evento):
        tipos[evento["requestId"]] = evento.get("type", "Other")

    def ao_terminar(evento):
        n = evento.get("encodedDataLength", 0) or 0
        medicao.requisicoes += 1
        medicao.bytes_rede += n
        tipo = tipos.get(evento["requestId"], "Other")
        medicao.por_tipo[tipo] = medicao.por_tipo.get(tipo, 0) + n

    cdp.on("Network.responseReceived", ao_responder)
    cdp.on("Network.loadingFinished", ao_terminar)


def bytes_no_proxy(desde: float) -> int | None:
    """Bytes que o proxy entregou ao cliente depois de `desde`, ou seja o faturado.

    Devolve `None` quando o proxy não deixou rastro nenhum, para o script seguir
    medindo só o lado cliente em vez de quebrar.
    """
    time.sleep(ESPERA_LOG_SQUID)
    try:
        saida = subprocess.run(
            ["docker", "compose", "logs", "--no-log-prefix", "proxy"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return None

    if not saida.strip():
        return None

    total = 0
    for linha in saida.splitlines():
        # Campos do `logformat bytes` lá do squid.conf: hora, duração, ip,
        # resultado/status, bytes, método, url, usuário.
        m = re.match(r"^(\d+\.\d+)\s+\d+\s+\S+\s+\S+\s+(\d+)\s+", linha)
        if m and float(m.group(1)) >= desde:
            total += int(m.group(2))
    return total


def imprimir(medicao: Medicao, proxy: int | None = None) -> None:
    print(f"\n{medicao.rotulo}")
    print(f"  requisições concluídas : {medicao.requisicoes}")
    if medicao.bloqueadas:
        print(f"  requisições bloqueadas : {medicao.bloqueadas}")
    print(f"  bytes na rede (cliente): {medicao.bytes_rede:>9,} B  = {medicao.kib:.1f} KiB")
    if proxy is not None:
        print(f"  bytes no proxy (faturado): {proxy:>7,} B  = {proxy / 1024:.1f} KiB")
    if medicao.por_tipo:
        print("  por tipo:")
        for tipo, n in sorted(medicao.por_tipo.items(), key=lambda kv: -kv[1])[:6]:
            print(f"    {tipo:<12} {n:>9,} B")

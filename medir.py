"""Roda os cenários e cospe a tabela.

    uv run python medir.py

Precisa do proxy no ar: `just up`.
"""

import time

from playwright.sync_api import sync_playwright

from comum import (
    ALVO,
    BLOQUEADOS_CDP,
    PROXY,
    PROXY_SENHA,
    PROXY_USUARIO,
    Medicao,
    bytes_no_proxy,
    contar_bytes,
    exigir_proxy,
)

# O segundo eixo: bloquear e tirar do proxy são perguntas diferentes. Num alvo
# real entrariam aqui o CDN de estáticos, o analytics e a fonte hospedada fora.
# `books.toscrape.com` não carrega um único domínio de terceiro, então o demo
# tira o próprio alvo do proxy, o que não se faria em produção e só serve pra
# mostrar o mecanismo.
#
# A lista é separada por `;`, que também separa parâmetro em query string, então
# URL com query precisa ser codificada.
FORA_DO_PROXY = "books.toscrape.com"

CENARIOS = [
    ("baseline", False, False),
    ("só bloqueio", True, False),
    ("bloqueio + bypass", True, True),
]


def rodar(rotulo: str, bloquear: bool, bypass: bool) -> tuple[Medicao, int | None]:
    medicao = Medicao(rotulo=rotulo)
    args = [f"--proxy-bypass-list={FORA_DO_PROXY}"] if bypass else []
    inicio = time.time()

    with sync_playwright() as p:
        navegador = p.chromium.launch(proxy=PROXY, args=args)
        contexto = navegador.new_context()
        pagina = contexto.new_page()
        cdp = contexto.new_cdp_session(pagina)
        contar_bytes(cdp, medicao)

        cdp.send("Fetch.enable", {"handleAuthRequests": True, "patterns": [{"urlPattern": "*"}]})
        cdp.on(
            "Fetch.authRequired",
            lambda e: cdp.send(
                "Fetch.continueWithAuth",
                {
                    "requestId": e["requestId"],
                    "authChallengeResponse": {
                        "response": "ProvideCredentials",
                        "username": PROXY_USUARIO,
                        "password": PROXY_SENHA,
                    },
                },
            ),
        )

        def pausada(evento):
            if bloquear and evento.get("resourceType") in BLOQUEADOS_CDP:
                medicao.bloqueadas += 1
                cdp.send(
                    "Fetch.failRequest",
                    {"requestId": evento["requestId"], "errorReason": "BlockedByClient"},
                )
            else:
                cdp.send("Fetch.continueRequest", {"requestId": evento["requestId"]})

        cdp.on("Fetch.requestPaused", pausada)
        pagina.goto(ALVO, wait_until="networkidle")
        navegador.close()

    return medicao, bytes_no_proxy(desde=inicio)


def delta(atual: float, base: float) -> str:
    return "-" if not base or atual == base else f"{atual / base - 1:.1%}"


def main() -> None:
    exigir_proxy()
    print(f"alvo: {ALVO}\n")

    linhas = []
    for rotulo, bloquear, bypass in CENARIOS:
        medicao, proxy = rodar(rotulo, bloquear, bypass)
        linhas.append((medicao, proxy))
        print(f"  {medicao.rotulo:<18} {medicao.requisicoes:>3} req  {medicao.kib:>7.1f} KiB")

    base = linhas[0][0].bytes_rede
    print("\n| Cenário | Requisições | Banda (KiB) | Delta |")
    print("| --- | ---: | ---: | ---: |")
    for medicao, _ in linhas:
        campos = f"{medicao.requisicoes} | {medicao.kib:.1f} | {delta(medicao.bytes_rede, base)}"
        print(f"| {medicao.rotulo} | {campos} |")

    if all(proxy is not None for _, proxy in linhas):
        base_proxy = linhas[0][1]
        print("\n| Cenário | Faturado pelo proxy (KiB) | Delta |")
        print("| --- | ---: | ---: |")
        for medicao, proxy in linhas:
            print(f"| {medicao.rotulo} | {proxy / 1024:.1f} | {delta(proxy, base_proxy)} |")
    print()


if __name__ == "__main__":
    main()

"""Roda os cenários e cospe a tabela.

    uv run python medir.py

Precisa do proxy no ar: `just up`.
"""

from __future__ import annotations

import time

from playwright.sync_api import sync_playwright

from comum import (
    ALVO,
    BLOQUEADOS_CDP,
    PROXY_HOST,
    PROXY_PORTA,
    PROXY_SENHA,
    PROXY_USUARIO,
    Medicao,
    bytes_no_proxy,
    contar_bytes,
)

PROXY = {
    "server": f"http://{PROXY_HOST}:{PROXY_PORTA}",
    "username": PROXY_USUARIO,
    "password": PROXY_SENHA,
}

# O segundo eixo: bloquear e tirar do proxy são perguntas diferentes.
#
# Num alvo real você listaria aqui o CDN de estáticos, o analytics e a fonte
# hospedada fora, que a página precisa carregar mas não precisam sair pelo seu
# IP pago. Esse é o dinheiro que ninguém pega.
#
# `books.toscrape.com` é simples demais para isso: ele não carrega um único
# domínio de terceiro. Então o demo tira o PRÓPRIO alvo do proxy, que não é o
# que se faria em produção, mas mostra o mecanismo: o cliente baixa igual, e o
# proxy não fatura nada.
#
# Cuidado com a sintaxe: a lista é separada por `;`, e `;` também é separador de
# parâmetro em query string. URL com query precisa ser codificada.
FORA_DO_PROXY = "books.toscrape.com"


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


CENARIOS = [
    ("baseline", False, False),
    ("só bloqueio", True, False),
    ("bloqueio + tudo DIRECT", True, True),
]


def main() -> None:
    print(f"alvo: {ALVO}\n")
    linhas = []
    for rotulo, bloquear, bypass in CENARIOS:
        medicao, proxy = rodar(rotulo, bloquear, bypass)
        linhas.append((rotulo, medicao, proxy))
        print(f"  {rotulo:<20} {medicao.requisicoes:>3} req  {medicao.kib:>7.1f} KiB")

    base = linhas[0][1].bytes_rede
    print("\n| Cenário | Requisições | Banda (KiB) | Delta |")
    print("| --- | ---: | ---: | ---: |")
    for rotulo, medicao, _ in linhas:
        delta = "-" if medicao.bytes_rede == base else f"{medicao.bytes_rede / base - 1:.1%}"
        print(f"| {rotulo} | {medicao.requisicoes} | {medicao.kib:.1f} | {delta} |")

    if all(p is not None for _, _, p in linhas):
        base_proxy = linhas[0][2]
        print("\n| Cenário | Faturado pelo proxy (KiB) | Delta |")
        print("| --- | ---: | ---: |")
        for rotulo, _, proxy in linhas:
            delta = "-" if proxy == base_proxy else f"{proxy / base_proxy - 1:.1%}"
            print(f"| {rotulo} | {proxy / 1024:.1f} | {delta} |")
    print()


if __name__ == "__main__":
    main()

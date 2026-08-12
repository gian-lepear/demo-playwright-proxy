"""A solução conhecida: `context.route` com `abort()`, sem proxy nenhum.

Funciona. Oito linhas e a banda cai. Se o seu caso é esse, pare aqui.

    uv run python 01_ingenuo.py
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from comum import ALVO, BLOQUEADOS_ROUTE, Medicao, contar_bytes, imprimir


def rodar(bloquear: bool) -> Medicao:
    rotulo = "com bloqueio (context.route)" if bloquear else "baseline (nada bloqueado)"
    medicao = Medicao(rotulo=rotulo)

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto = navegador.new_context()
        pagina = contexto.new_page()
        contar_bytes(contexto.new_cdp_session(pagina), medicao)

        if bloquear:

            def filtrar(rota, requisicao):
                if requisicao.resource_type in BLOQUEADOS_ROUTE:
                    medicao.bloqueadas += 1
                    rota.abort()
                else:
                    rota.continue_()

            contexto.route("**/*", filtrar)

        pagina.goto(ALVO, wait_until="networkidle")
        navegador.close()

    return medicao


if __name__ == "__main__":
    base = rodar(bloquear=False)
    imprimir(base)

    corte = rodar(bloquear=True)
    imprimir(corte)

    economia = 1 - (corte.bytes_rede / base.bytes_rede) if base.bytes_rede else 0
    print(f"\neconomia: {economia:.1%}\n")

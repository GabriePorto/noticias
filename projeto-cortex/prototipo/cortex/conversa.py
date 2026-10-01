"""Console para conversar com o robô em tempo real.

    python -m cortex.conversa            # compreensão com o Claude (precisa de chave da API)
    python -m cortex.conversa --offline  # só palavras-chave, sem rede

Cada frase digitada é ouvida pelo robô. A simulação roda 6 segundos depois de cada
fala (ou até ele terminar a tarefa) e mostra as mensagens de decisão e o que ele falou.
Comandos: /estado mostra o robô, /liberar libera uma parada (como dono), /sair encerra.
"""
from __future__ import annotations

import json
import sys

from .cerebro import Cerebro
from .linguagem import InterpretadorClaude, InterpretadorPalavras
from .mundo import Mundo, Pessoa


def main(argv: list[str]) -> None:
    try:
        interp = InterpretadorPalavras() if "--offline" in argv else InterpretadorClaude()
    except RuntimeError as erro:
        sys.exit(str(erro))
    mundo = Mundo()
    mundo.pessoas["p_ana"] = Pessoa("p_ana", "Ana", 3.2, 4.4, consentimento=True)
    c = Cerebro(mundo, interpretador=interp)
    print(f"Robô ligado · linguagem: {interp.nome} · Ana está na sala. Digite /sair para encerrar.")
    visto = 0
    while True:
        try:
            texto = input("\nvocê › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not texto:
            continue
        if texto == "/sair":
            break
        if texto == "/estado":
            print(json.dumps(mundo.foto()["robo"], ensure_ascii=False))
            continue
        if texto == "/liberar":
            c.externo("DONO", "SC-00", "modulador", "liberar", prioridade=0)
            c.rodar(c.t_ms / 1000 + 0.05)
            print("Parada liberada pelo dono.")
            continue
        falas_antes = len(mundo.falas)
        c.ouvir(texto)
        limite = c.t_ms / 1000 + 20
        ocioso = 0.0
        while c.t_ms / 1000 < limite:
            c.rodar(c.t_ms / 1000 + 0.5)
            ocupado = c.modulos["BG-00"].atual is not None or c.modulos["CTX-M1"].acao is not None
            ocioso = 0.0 if ocupado else ocioso + 0.5
            if ocioso >= 1.0 and len(mundo.falas) > falas_antes:
                break
        for m in c.bus.registro[visto:]:
            print(f"  {m.t / 1000:7.3f} s  P{m.prioridade}  {m.de:>7} → {m.para:<7} {m.sinal} "
                  f"{json.dumps({k: v for k, v in m.dados.items() if k != 'texto'}, ensure_ascii=False)}")
        visto = len(c.bus.registro)
        for _, fala in mundo.falas[falas_antes:]:
            print(f"robô › {fala}")


if __name__ == "__main__":
    main(sys.argv[1:])

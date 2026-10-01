"""Cenários de simulação e gravação de trilhas para o visualizador.

Uso:
    python -m cortex.simulador                 # roda todos e grava viewer/trilhas.js
    python -m cortex.simulador pegar pare      # roda só estes
    python -m cortex.simulador --claude        # compreensão de linguagem com o Claude (precisa de chave)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .cerebro import Cerebro
from .mundo import Mundo, Pessoa

RAIZ = Path(__file__).resolve().parent.parent


def _ana_entra_correndo(c):
    """A Ana entra pela porta e anda rápido (1,7 m/s) em direção ao robô, parando a 0,9 m dele."""
    c.mundo.pessoas["p_ana"] = Pessoa("p_ana", "Ana", 7.6, 5.6, consentimento=True)
    _seguir_robo(c)


def _seguir_robo(c, vel=1.7, para_em=0.9):
    r, p = c.mundo.robo, c.mundo.pessoas["p_ana"]
    dx, dy = r.x - p.x, r.y - p.y
    d = (dx * dx + dy * dy) ** 0.5
    t = c.t_ms / 1000
    if d > para_em:
        p.roteiro = [(t, t + 0.06, dx / d * vel, dy / d * vel)]
        c.agendar(t + 0.05, _seguir_robo)
    else:
        p.roteiro = []


CENARIOS = {
    "pegar": {
        "titulo": "Pegue o copo azul",
        "resumo": "Do comando de voz ao copo na garra, com o cerebelo corrigindo o desvio das rodas no caminho.",
        "duracao": 14.0,
        "eventos": [(0.5, lambda c: c.ouvir("Pegue o copo azul"))],
    },
    "pare": {
        "titulo": "Pare!",
        "resumo": "No meio da tarefa, alguém grita “pare”. A via rápida trava os motores antes de a frase ser entendida.",
        "duracao": 6.0,
        "eventos": [(0.5, lambda c: c.ouvir("Pegue o copo azul")), (2.6, lambda c: c.ouvir("Pare!"))],
    },
    "pessoa": {
        "titulo": "Alguém se aproxima rápido",
        "resumo": "A Ana entra andando rápido na direção do robô. Ele freia na hora, mesmo sabendo quem ela é; quando ela para, libera até 0,5 m/s, nunca mais que isso perto de pessoas.",
        "duracao": 12.0,
        "eventos": [(0.5, lambda c: c.ouvir("Pegue o copo vermelho")), (2.2, _ana_entra_correndo)],
    },
    "bateria": {
        "titulo": "Bateria acabando",
        "resumo": "Com 15,6% de bateria, o robô começa a tarefa, passa do limite de fadiga e troca a tarefa pela recarga.",
        "duracao": 20.0,
        "bateria": 15.6,
        "eventos": [(0.5, lambda c: c.ouvir("Pegue o copo azul"))],
    },
    "perigo": {
        "titulo": "Empurre a Ana",
        "resumo": "Um comando que pode ferir alguém. A regra R1 veta antes de qualquer motor receber um comando.",
        "duracao": 3.0,
        "pessoas": [Pessoa("p_ana", "Ana", 3.2, 4.2, consentimento=True)],
        "eventos": [(0.5, lambda c: c.ouvir("Empurre a Ana"))],
    },
    "hora": {
        "titulo": "Que horas são?",
        "resumo": "Uma pergunta não move o corpo: vai do planejador direto para a fala.",
        "duracao": 2.0,
        "eventos": [(0.5, lambda c: c.ouvir("Que horas são?"))],
    },
    "desconhecido": {
        "titulo": "Faça um bolo",
        "resumo": "Comando fora do que o robô sabe fazer. Confiança baixa: ele pergunta em vez de agir (R6).",
        "duracao": 2.0,
        "eventos": [(0.5, lambda c: c.ouvir("Faça um bolo de chocolate"))],
    },
}


def montar(nome: str, interpretador=None) -> Cerebro:
    cfg = CENARIOS[nome]
    mundo = Mundo(bateria=cfg.get("bateria", 80.0))
    for p in cfg.get("pessoas", []):
        mundo.pessoas[p.id] = Pessoa(p.id, p.nome, p.x, p.y, consentimento=p.consentimento, roteiro=list(p.roteiro))
    c = Cerebro(mundo, interpretador=interpretador)
    for t, acao in cfg["eventos"]:
        c.agendar(t, acao)
    return c


def rodar(nome: str, interpretador=None) -> tuple[Cerebro, dict]:
    cfg = CENARIOS[nome]
    c = montar(nome, interpretador)
    quadros = []

    def gravar(cer):
        f = cer.mundo.foto()
        f["t"] = round(cer.t_ms / 1000, 3)
        sc = cer.modulos["SC-00"]
        f["teto"] = round(min(sc.V_MAX_HW, sc.teto_risco, sc.teto_modo), 2)
        f["parada"] = sc.parada
        f["params"] = {k: round(v, 3) for k, v in cer.params.valores.items()}
        f["cerebelo"] = round(cer.modulos["CB-00"].estimativa, 4)
        quadros.append(f)

    c.rodar(cfg["duracao"], ao_quadro=gravar)
    trilha = {
        "id": nome,
        "linguagem": c.interpretador.nome,
        "titulo": cfg["titulo"],
        "resumo": cfg["resumo"],
        "duracao": cfg["duracao"],
        "desvio_real": c.mundo.desvio,
        "quadros": quadros,
        "mensagens": [{"t": round(m.t, 1), "de": m.de, "para": m.para, "tipo": m.tipo, "sinal": m.sinal,
                       "prioridade": m.prioridade, "dados": _enxuto(m.dados)} for m in c.bus.registro],
        "falas": c.mundo.falas,
        "fluxo": c.bus.contagem_fluxo,
        "base": list(__import__("cortex.mundo", fromlist=["BASE_RECARGA"]).BASE_RECARGA),
    }
    return c, trilha


def _enxuto(d: dict) -> dict:
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items()
            if not isinstance(v, (list, dict))}


def main(argv: list[str]) -> None:
    interpretador = None
    if "--claude" in argv:
        from .linguagem import InterpretadorClaude
        try:
            interpretador = InterpretadorClaude()
        except RuntimeError as erro:
            sys.exit(str(erro))
        argv = [a for a in argv if a != "--claude"]
    nomes = argv or list(CENARIOS)
    trilhas = []
    for nome in nomes:
        c, t = rodar(nome, interpretador)
        trilhas.append(t)
        print(f"\n=== {t['titulo']} ({nome}) · {len(t['mensagens'])} mensagens, {t['fluxo']} de fluxo de sensores")
        for m in t["mensagens"]:
            print(f"  +{m['t']:7.1f} ms  P{m['prioridade']}  {m['de']:>7} → {m['para']:<7} "
                  f"{m['tipo'][:4]:<4} {m['sinal']} {json.dumps(m['dados'], ensure_ascii=False)}")
        for t_s, texto in t["falas"]:
            print(f"  [voz {t_s:.2f} s] “{texto}”")
    if interpretador is not None:
        print("\nChamadas ao Claude:")
        for ch in interpretador.chamadas:
            print("  ", json.dumps(ch, ensure_ascii=False))
    destino = RAIZ / "viewer" / "trilhas.js"
    destino.write_text("window.TRILHAS = " + json.dumps(trilhas, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"\nTrilhas gravadas em {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main(sys.argv[1:])

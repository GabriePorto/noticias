"""Barramento de mensagens: a "sinapse do robô" (Etapa 4).

Toda comunicação entre módulos passa por aqui, no formato do protocolo:
de, para, tipo, sinal, prioridade, dados, peso, ttl_ms e t.
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field, asdict

TIPOS = ("dados", "excitatorio", "inibitorio", "modulador")


@dataclass
class Mensagem:
    de: str
    para: str
    tipo: str
    sinal: str
    dados: dict = field(default_factory=dict)
    prioridade: int = 5
    peso: float = 1.0
    ttl_ms: int = 500
    t: float = 0.0          # instante de emissão (ms de simulação)
    id: str = ""
    fluxo: bool = False     # mensagens de alta frequência (sensores); não entram no resumo

    def como_dict(self) -> dict:
        d = asdict(self)
        d.pop("fluxo")
        return d


class Barramento:
    """Entrega mensagens em ordem de horário e, no mesmo horário, de prioridade (P0 primeiro).

    Descarta mensagens vencidas (ttl_ms) e registra tudo o que não é fluxo de sensor (regra R8).
    """

    def __init__(self, relogio):
        self.relogio = relogio          # função que devolve o tempo atual em ms
        self._fila: list = []
        self._seq = itertools.count()
        self._n = itertools.count(1)
        self.destinos: dict = {}
        self.registro: list[Mensagem] = []
        self.descartadas: list[Mensagem] = []
        self.contagem_fluxo = 0

    def registrar_destino(self, codigo: str, receptor) -> None:
        self.destinos[codigo] = receptor

    def publicar(self, msg: Mensagem, atraso_ms: float = 0.0) -> Mensagem:
        if msg.tipo not in TIPOS:
            raise ValueError(f"tipo de sinal inválido: {msg.tipo}")
        if msg.para not in self.destinos:
            raise KeyError(f"destino desconhecido: {msg.para}")
        if not 0 <= msg.prioridade <= 5:
            raise ValueError("prioridade deve ser de 0 a 5")
        agora = self.relogio()
        msg.t = agora
        msg.id = f"m-{next(self._n):06d}"
        entrega = agora + max(0.0, atraso_ms)
        heapq.heappush(self._fila, (entrega, msg.prioridade, next(self._seq), msg))
        if msg.fluxo:
            self.contagem_fluxo += 1
        else:
            self.registro.append(msg)
        return msg

    def entregar_pendentes(self, limite: int = 10_000) -> int:
        """Entrega tudo o que venceu até agora. Mensagens publicadas durante a entrega
        com atraso zero são entregues na mesma rodada."""
        agora = self.relogio()
        n = 0
        while self._fila and self._fila[0][0] <= agora + 1e-9:
            _, _, _, msg = heapq.heappop(self._fila)
            if agora - msg.t > msg.ttl_ms:
                self.descartadas.append(msg)
                continue
            self.destinos[msg.para].receber(msg)
            n += 1
            if n > limite:
                raise RuntimeError("laço de mensagens sem fim: falta inibição (ver NT-GLU·GABA)")
        return n

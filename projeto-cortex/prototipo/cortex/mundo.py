"""Mundo simulado: uma sala 8 m × 6 m vista de cima.

O robô é uma base com rodas (modelo uniciclo) com uma garra. Os atuadores têm um
desvio sistemático (as rodas puxam para um lado), que o cerebelo precisa aprender a
compensar. Só o módulo SC-00 escreve nos atuadores.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

LARGURA, ALTURA = 8.0, 6.0
ACEL_MAX = 3.0          # m/s², limite físico dos motores
BASE_RECARGA = (0.7, 0.7)


@dataclass
class Robo:
    x: float = 1.5
    y: float = 3.0
    theta: float = 0.0
    v: float = 0.0
    w: float = 0.0
    segurando: str | None = None
    bateria: float = 80.0
    carregando: bool = False
    distancia: float = 0.0


@dataclass
class Objeto:
    id: str
    tipo: str
    cor: str
    x: float
    y: float
    preso: bool = False


@dataclass
class Pessoa:
    id: str
    nome: str
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    consentimento: bool = False     # R9: só reconhecida pelo nome com consentimento
    roteiro: list = field(default_factory=list)   # [(t_ini, t_fim, vx, vy)]


class Mundo:
    def __init__(self, semente: int = 7, desvio_rad: float = 0.12, bateria: float = 80.0):
        self.rng = random.Random(semente)
        self.desvio = desvio_rad
        self.robo = Robo(bateria=bateria)
        self.objetos = {
            "copo_01": Objeto("copo_01", "copo", "azul", 6.2, 4.4),
            "copo_02": Objeto("copo_02", "copo", "vermelho", 6.0, 1.3),
            "caixa_01": Objeto("caixa_01", "caixa", "verde", 3.8, 5.0),
        }
        self.pessoas: dict[str, Pessoa] = {}
        self.falas: list[tuple[float, str]] = []
        self.t = 0.0

    # ------------------------------------------------------------ atuadores
    def aplicar(self, v_cmd: float, w_cmd: float, dt: float) -> None:
        r = self.robo
        dv = max(-ACEL_MAX * dt, min(ACEL_MAX * dt, v_cmd - r.v))
        r.v += dv
        r.w = w_cmd
        if r.carregando:
            r.v = r.w = 0.0

    def fechar_garra(self) -> float:
        """Tenta pegar o objeto mais próximo. Devolve a força de contato em newtons."""
        r = self.robo
        if r.segurando or abs(r.v) > 0.05:
            return 0.0
        alvo = min(self.objetos.values(), key=lambda o: math.dist((o.x, o.y), (r.x, r.y)))
        if math.dist((alvo.x, alvo.y), (r.x, r.y)) < 0.3:
            alvo.preso = True
            r.segurando = alvo.id
            return 3.2
        return 0.0

    # ------------------------------------------------------------ física
    def passo(self, dt: float) -> None:
        self.t += dt
        r = self.robo
        ang = r.theta + (self.desvio if abs(r.v) > 1e-3 else 0.0)
        r.x = min(LARGURA - 0.2, max(0.2, r.x + r.v * math.cos(ang) * dt))
        r.y = min(ALTURA - 0.2, max(0.2, r.y + r.v * math.sin(ang) * dt))
        r.theta = (r.theta + r.w * dt + math.pi) % (2 * math.pi) - math.pi
        r.distancia += abs(r.v) * dt
        if r.segurando:
            o = self.objetos[r.segurando]
            o.x, o.y = r.x + 0.18 * math.cos(r.theta), r.y + 0.18 * math.sin(r.theta)
        consumo = 0.05 + 0.35 * abs(r.v)            # % por segundo
        if r.carregando:
            r.bateria = min(100.0, r.bateria + 2.0 * dt)
        else:
            r.bateria = max(0.0, r.bateria - consumo * dt)
        for p in self.pessoas.values():
            p.vx = p.vy = 0.0
            for t0, t1, vx, vy in p.roteiro:
                if t0 <= self.t < t1:
                    p.vx, p.vy = vx, vy
            p.x += p.vx * dt
            p.y += p.vy * dt

    # ------------------------------------------------------------ sensores
    def quadro_camera(self) -> dict:
        """O que as câmeras veem: objetos e pessoas com posição (e um pouco de ruído)."""
        ru = lambda: self.rng.gauss(0, 0.01)
        return {
            "objetos": [{"id": o.id, "tipo": o.tipo, "cor": o.cor, "x": o.x + ru(), "y": o.y + ru(),
                         "preso": o.preso} for o in self.objetos.values()],
            "pessoas": [{"id": p.id, "x": p.x + ru(), "y": p.y + ru(), "vx": p.vx, "vy": p.vy,
                         "consentimento": p.consentimento, "nome": p.nome} for p in self.pessoas.values()],
        }

    def distancia_pessoa_mais_proxima(self) -> float:
        r = self.robo
        return min((math.dist((p.x, p.y), (r.x, r.y)) for p in self.pessoas.values()), default=99.0)

    def na_base(self) -> bool:
        return math.dist(BASE_RECARGA, (self.robo.x, self.robo.y)) < 0.3

    def foto(self) -> dict:
        r = self.robo
        return {
            "robo": {"x": round(r.x, 3), "y": round(r.y, 3), "theta": round(r.theta, 3), "v": round(r.v, 3),
                     "segurando": r.segurando, "bateria": round(r.bateria, 2), "carregando": r.carregando},
            "objetos": [{"id": o.id, "tipo": o.tipo, "cor": o.cor, "x": round(o.x, 3), "y": round(o.y, 3)}
                        for o in self.objetos.values()],
            "pessoas": [{"id": p.id, "nome": p.nome, "x": round(p.x, 3), "y": round(p.y, 3)}
                        for p in self.pessoas.values()],
        }

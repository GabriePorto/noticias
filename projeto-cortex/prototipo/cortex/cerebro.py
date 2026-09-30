"""Monta o cérebro a partir da especificação (spec/cortex.json) e roda o relógio."""
from __future__ import annotations

import json
from pathlib import Path

from .bus import Barramento, Mensagem
from .modulos import IMPLEMENTADOS, Passivo
from .mundo import Mundo
from .parametros import Parametros

SPEC_PADRAO = Path(__file__).resolve().parent.parent / "spec" / "cortex.json"

# Pontas físicas que não são módulos do cérebro: sensores, atuadores e pessoas.
PSEUDO = ("MIC", "CAM", "VOZ", "MOTORES", "BATERIA", "DONO")


class Pseudo:
    def __init__(self, cerebro, codigo):
        self.c, self.codigo = cerebro, codigo

    def receber(self, msg: Mensagem):
        if self.codigo == "VOZ":
            self.c.mundo.falas.append((round(self.c.t_ms / 1000, 3), msg.dados["texto"]))


def carregar_spec(caminho: Path | str = SPEC_PADRAO) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


class Cerebro:
    def __init__(self, mundo: Mundo | None = None, spec: dict | None = None, dt: float = 0.005):
        self.spec = spec or carregar_spec()
        self.componentes = {c["codigo"]: c for c in self.spec["componentes"]}
        self.dt = dt
        self.t_ms = 0.0
        self.bus = Barramento(lambda: self.t_ms)
        self.params = Parametros(self.spec)
        self.mundo = mundo or Mundo()
        self.periodo_camera_ms = 1000 / 30
        self._ultima_camera = -1e9
        self.agenda: list[tuple[float, callable]] = []
        self.modulos = {}
        for codigo in self.componentes:
            cls = IMPLEMENTADOS.get(codigo)
            mod = cls(self) if cls else Passivo(self, codigo)
            self.modulos[codigo] = mod
            self.bus.registrar_destino(codigo, mod)
        for codigo in PSEUDO:
            self.bus.registrar_destino(codigo, Pseudo(self, codigo))

    # ------------------------------------------------------------ entradas externas
    def externo(self, de, para, tipo, sinal, dados=None, prioridade=2):
        return self.bus.publicar(Mensagem(de, para, tipo, sinal, dict(dados or {}), prioridade))

    def ouvir(self, texto: str):
        """Alguém fala com o robô."""
        return self.externo("MIC", "CTX-A1", "dados", "audio.stream", {"texto": texto, "canais": 4})

    def agendar(self, t_s: float, acao):
        self.agenda.append((t_s, acao))
        self.agenda.sort(key=lambda x: x[0])

    # ------------------------------------------------------------ relógio
    def passo(self):
        self.t_ms += self.dt * 1000
        agora = self.t_ms / 1000
        while self.agenda and self.agenda[0][0] <= agora:
            self.agenda.pop(0)[1](self)
        if self.t_ms - self._ultima_camera >= self.periodo_camera_ms - 1e-6:
            self._ultima_camera = self.t_ms
            q = self.mundo.quadro_camera()
            r = self.mundo.robo
            q["eu"] = {"x": r.x, "y": r.y, "theta": r.theta}
            m = Mensagem("CAM", "DIE-TH", "dados", "sensor.camera", q, 2, ttl_ms=100, fluxo=True)
            self.bus.publicar(m)
        self.bus.entregar_pendentes()
        for mod in self.modulos.values():
            mod.passo(self.dt)
        self.bus.entregar_pendentes()
        self.mundo.passo(self.dt)
        self.params.passo(agora, self.dt)

    def rodar(self, ate_s: float, ao_quadro=None, cada_s: float = 0.05):
        proximo = 0.0
        while self.t_ms / 1000 < ate_s - 1e-9:
            self.passo()
            if ao_quadro and self.t_ms / 1000 >= proximo - 1e-9:
                ao_quadro(self)
                proximo += cada_s

"""Parâmetros globais: a neuroquímica do robô (Etapas 3 e 4)."""
from __future__ import annotations


class PermissaoNegada(Exception):
    """Tentativa de alterar um parâmetro sem permissão. Carrega a regra violada."""

    def __init__(self, regra: str, texto: str):
        super().__init__(f"{regra}: {texto}")
        self.regra = regra


# Quem pode escrever em cada parâmetro. Origem é um código de módulo ou um papel humano.
ESCRITORES = {
    "alerta": {"LIM-AM", "DIE-HY"},
    "foco": {"CTX-PF"},
    "paciencia": {"DONO"},
    "fadiga": {"DIE-HY"},
    "recompensa": {"MB-SN"},                 # R5: nenhum comando externo altera
    "confianca": {"DONO", "CTX-PF"},
    "supressao": {"CTX-PF"},                 # R7: expira sozinha
    "ganho": {"ENGENHARIA"},
}
REGRA_DE = {"recompensa": "R5", "ganho": "Permissões", "fadiga": "Permissões"}
SUPRESSAO_VALIDADE_S = 60.0
ALERTA_REPOUSO = 0.3


class Parametros:
    def __init__(self, spec: dict):
        self.faixas: dict[str, tuple[float, float]] = {}
        self.valores: dict[str, float] = {}
        for c in spec["componentes"]:
            p = c["comandos"].get("parametro")
            if p:
                self.faixas[p["nome"]] = (p["minimo"], p["maximo"])
                self.valores[p["nome"]] = p["padrao"]
        self._supressao_ate: float | None = None
        self._alerta_em = 0.0
        self.historico: list[tuple[float, str, float, str]] = []

    def __getitem__(self, nome: str) -> float:
        return self.valores[nome]

    def definir(self, nome: str, valor: float, origem: str, agora_s: float) -> float:
        if nome not in self.valores:
            raise KeyError(nome)
        if origem not in ESCRITORES[nome]:
            raise PermissaoNegada(REGRA_DE.get(nome, "Permissões"),
                                  f"{origem} não pode alterar '{nome}'")
        lo, hi = self.faixas[nome]
        v = min(hi, max(lo, float(valor)))
        self.valores[nome] = v
        if nome == "supressao":
            self._supressao_ate = agora_s + SUPRESSAO_VALIDADE_S if v > 0 else None
        if nome == "alerta":
            self._alerta_em = agora_s
        self.historico.append((agora_s, nome, v, origem))
        return v

    def passo(self, agora_s: float, dt: float) -> None:
        # R7: toda supressão expira.
        if self._supressao_ate is not None and agora_s >= self._supressao_ate:
            self.valores["supressao"] = 0.0
            self._supressao_ate = None
            self.historico.append((agora_s, "supressao", 0.0, "expirou"))
        # Alerta volta sozinho ao repouso 2 s depois do último ajuste.
        a = self.valores["alerta"]
        if agora_s - self._alerta_em > 2.0 and abs(a - ALERTA_REPOUSO) > 1e-3:
            passo = 0.05 * dt
            self.valores["alerta"] = a - passo if a > ALERTA_REPOUSO else a + passo

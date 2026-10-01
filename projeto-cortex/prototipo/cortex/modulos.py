"""Os módulos do cérebro do robô (Etapa 3), cada um com o código do atlas.

Regra da casa: um módulo nunca lê o estado interno de outro. Tudo passa pelo
barramento, como mensagem. As exceções são as interfaces físicas: SC-00 é o único
que escreve nos atuadores (R3, R4) e DIE-HY é o único que liga o carregador.

Os atrasos (atraso=...) imitam o tempo de processamento real de cada etapa.
"""
from __future__ import annotations

import math
import re
import unicodedata

from .bus import Mensagem
from .mundo import BASE_RECARGA


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def angulo(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


class Modulo:
    codigo = "?"

    def __init__(self, cerebro, codigo: str | None = None):
        self.c = cerebro
        if codigo:
            self.codigo = codigo
        comp = cerebro.componentes.get(self.codigo, {})
        p = comp.get("comandos", {}).get("prioridade")
        self.prioridade = p if p is not None else 4
        self.recebidas = 0

    @property
    def agora_s(self) -> float:
        return self.c.t_ms / 1000.0

    def pub(self, para, tipo, sinal, dados=None, atraso=0.0, fluxo=False, prioridade=None, ttl=500):
        msg = Mensagem(self.codigo, para, tipo, sinal, dict(dados or {}),
                       self.prioridade if prioridade is None else prioridade, ttl_ms=ttl, fluxo=fluxo)
        return self.c.bus.publicar(msg, atraso)

    def receber(self, msg: Mensagem) -> None:
        self.recebidas += 1
        h = getattr(self, "on_" + msg.sinal.replace(".", "_"), None)
        if h:
            h(msg)

    def passo(self, dt: float) -> None:
        pass


class Passivo(Modulo):
    """Módulo ainda sem comportamento no protótipo: recebe e registra."""


# ====================================================================== percepção
class CortexAuditivo(Modulo):
    codigo = "CTX-A1"
    PALAVRAS_PARADA = ("pare", "stop", "chega")

    def on_audio_stream(self, m):
        texto = m.dados["texto"]
        n = normalizar(texto)
        if any(re.search(rf"\b{p}\b", n) for p in self.PALAVRAS_PARADA):
            # Via rápida: detecção de palavra-chave, antes de entender a frase.
            self.pub("LIM-AM", "dados", "som.intenso", {"dB": 84, "palavra": "pare"}, atraso=10, prioridade=0)
        self.pub("CTX-WE", "dados", "fala.audio", {"texto": texto}, atraso=30)


class Wernicke(Modulo):
    """Compreensão de linguagem. O interpretador (Claude ou palavras-chave) vem do Cerebro.
    O atraso da mensagem é a latência real do interpretador."""
    codigo = "CTX-WE"

    def on_fala_audio(self, m):
        intencao, latencia_ms = self.c.interpretador.interpretar(m.dados["texto"])
        intencao = {**intencao, "texto": m.dados["texto"]}
        intencao.setdefault("origem", self.c.interpretador.nome)
        self.pub("CTX-PF", "dados", "intencao", intencao, atraso=latencia_ms, ttl=max(500, latencia_ms + 500))


class Talamo(Modulo):
    codigo = "DIE-TH"

    def __init__(self, cerebro):
        super().__init__(cerebro)
        self._ultimo_alerta = -9.0

    def on_sensor_camera(self, m):
        q = m.dados
        self.pub("CTX-OC", "dados", "visao.quadro", q, atraso=5, fluxo=True, ttl=100)
        eu = q["eu"]
        dmin, alerta = 99.0, None
        for p in q["pessoas"]:
            dx, dy = p["x"] - eu["x"], p["y"] - eu["y"]
            d = math.hypot(dx, dy)
            dmin = min(dmin, d)
            aprox = -(dx * p["vx"] + dy * p["vy"]) / max(d, 1e-6)
            if d < 1.6 and aprox > 0.8:
                alerta = {"id": p["id"], "dist_m": round(d, 2), "vel_ms": round(aprox, 2)}
        self.pub("LIM-AM", "dados", "pessoas.distancia", {"min_m": dmin}, fluxo=True, ttl=200)
        if alerta and self.agora_s - self._ultimo_alerta > 1.0:
            self._ultimo_alerta = self.agora_s
            # Via rápida para o detector de risco (o córtex só vai ver depois).
            self.pub("LIM-AM", "dados", "objeto.proximo", alerta, atraso=3, prioridade=0)

    def on_acao_liberada(self, m):
        self.pub("CTX-M1", "excitatorio", "executar", m.dados, atraso=5)

    def on_atencao_focar(self, m):
        self.foco = m.dados.get("alvo")


class CortexVisual(Modulo):
    codigo = "CTX-OC"

    def on_visao_quadro(self, m):
        self.pub("CTX-TE", "dados", "objetos", m.dados, atraso=30, fluxo=True, ttl=150)

    def on_broadcast_parametros(self, m):
        if "fps" in m.dados:
            self.c.periodo_camera_ms = 1000.0 / m.dados["fps"]


class Temporal(Modulo):
    codigo = "CTX-TE"

    def __init__(self, cerebro):
        super().__init__(cerebro)
        self._vistas: dict[str, float] = {}

    def on_objetos(self, m):
        q = m.dados
        self.pub("CTX-PA", "dados", "objeto.identificado", {"objetos": q["objetos"], "eu": q["eu"]},
                 atraso=20, fluxo=True, ttl=200)
        eu = q["eu"]
        for p in q["pessoas"]:
            if math.hypot(p["x"] - eu["x"], p["y"] - eu["y"]) > 2.5:
                continue        # rosto pequeno demais para reconhecer
            if self.agora_s - self._vistas.get(p["id"], -99) < 10:
                continue
            self._vistas[p["id"]] = self.agora_s
            # R9: só identifica pelo nome quem deu consentimento.
            conhecida = bool(p["consentimento"])
            self.pub("CTX-PF", "dados", "pessoa.reconhecida",
                     {"id": p["id"], "nome": p["nome"] if conhecida else None,
                      "conhecida": conhecida, "conf": 0.96 if conhecida else 0.0}, atraso=50)


class Parietal(Modulo):
    codigo = "CTX-PA"

    def on_objeto_identificado(self, m):
        mapa = {o["id"]: o for o in m.dados["objetos"]}
        for destino in ("CTX-M1", "CTX-PF"):
            self.pub(destino, "dados", "mapa.atualizado", {"mapa": mapa, "eu": m.dados["eu"]},
                     atraso=5, fluxo=True, ttl=300)


class Somatossensorial(Modulo):
    codigo = "CTX-S1"

    def on_tato(self, m):
        estado = "preso" if m.dados["forca_N"] > 1.0 else "vazio"
        for destino in ("CTX-PF", "CTX-M1"):
            self.pub(destino, "dados", "contato", {"estado": estado, "forca_N": m.dados["forca_N"]}, atraso=5)


# ====================================================================== valor e segurança
class Amigdala(Modulo):
    codigo = "LIM-AM"

    def __init__(self, cerebro):
        super().__init__(cerebro)
        self.teto = 1.0
        self._livre_desde = 0.0
        self._dmin = 99.0
        self.conhecidas: set[str] = set()
        self._proximo: dict | None = None

    def _alerta(self, v):
        self.c.params.definir("alerta", v, self.codigo, self.agora_s)
        self.pub("NT-NE", "modulador", "alerta", {"valor": v})

    def on_som_intenso(self, m):
        if m.dados.get("palavra") == "pare":
            self.pub("SC-00", "inibitorio", "parada.segura", {"categoria": "STOP_1"}, atraso=5, ttl=2000)
            self.pub("BG-00", "inibitorio", "cancelar.acoes", {}, atraso=5, ttl=2000)
            self._alerta(0.9)

    def on_objeto_proximo(self, m):
        # Freia primeiro, sem perguntar quem é.
        self._proximo = {"id": m.dados["id"], "t": self.agora_s}
        self._limitar(0.25, "inibitorio")
        self._alerta(0.7)

    def _limitar(self, teto, tipo):
        self.teto = teto
        self.pub("SC-00", tipo, "velocidade.limitar", {"max_ms": teto}, atraso=3, ttl=1000)

    def on_risco_reavaliar(self, m):
        if m.dados.get("conhecida"):
            self.conhecidas.add(m.dados["id"])

    def on_pessoas_distancia(self, m):
        self._dmin = m.dados["min_m"]
        px = self._proximo
        if px and self.teto <= 0.25 and px["id"] in self.conhecidas and self.agora_s - px["t"] > 0.8:
            # Pessoa conhecida e aproximação terminada: libera parte da velocidade,
            # mas nunca acima de 0,5 m/s perto de gente.
            self._proximo = None
            self._limitar(0.5, "modulador")
            self._alerta(0.4)
            return
        if self._dmin < 1.8:
            self._livre_desde = self.agora_s
            if self.teto > 0.5:
                self._limitar(0.5, "inibitorio")
        elif self.teto < 1.0 and self.agora_s - self._livre_desde > 2.0:
            self._limitar(1.0, "modulador")

    def on_risco_avaliar(self, m):
        d = m.dados
        if d.get("acao") == "contato_com_pessoa":
            resposta = {"nivel": 0.97, "dano_pessoa": True}
        else:
            nivel = 0.04 + (0.3 if self._dmin < 0.8 else 0.0)
            resposta = {"nivel": round(nivel, 2), "dano_pessoa": False}
        self.pub("CTX-PF", "dados", "risco", resposta, atraso=8)
        if resposta["dano_pessoa"]:
            self._alerta(0.6)


class Accumbens(Modulo):
    codigo = "BG-NA"
    UTILIDADE = {"pegar": 0.82, "ir_base": 0.95}

    def on_consulta_valor(self, m):
        self.pub("CTX-PF", "dados", "valor", {"acao": m.dados["acao"],
                                              "utilidade": self.UTILIDADE.get(m.dados["acao"], 0.5)}, atraso=8)


class SubstanciaNegra(Modulo):
    """Gera o erro de previsão de recompensa (aprendizado por reforço)."""
    codigo = "MB-SN"

    def __init__(self, cerebro):
        super().__init__(cerebro)
        self.previsto = {"pegar": 0.7}

    def on_resultado(self, m):
        acao = m.dados["acao"]
        r = 1.0 if m.dados["sucesso"] else 0.0
        v = self.previsto.get(acao, 0.5)
        erro = r - v
        self.previsto[acao] = v + 0.3 * erro
        self.c.params.definir("recompensa", erro, self.codigo, self.agora_s)
        self.pub("BG-00", "modulador", "recompensa", {"acao": acao, "erro_previsao": round(erro, 3)})


class Hipocampo(Modulo):
    codigo = "LIM-HC"

    def __init__(self, cerebro):
        super().__init__(cerebro)
        self.episodios: list[dict] = []
        self.consolidacoes = 0

    def on_registrar(self, m):
        self.episodios.append({"t": round(self.agora_s, 3), **m.dados})

    def on_consolidar(self, m):
        self.consolidacoes += 1
        self.resumo = {"episodios": len(self.episodios)}


# ====================================================================== deliberação
class PreFrontal(Modulo):
    codigo = "CTX-PF"
    CONF_MIN = 0.6          # R6
    RISCO_MAX = 0.3         # R1 e R6

    def __init__(self, cerebro):
        super().__init__(cerebro)
        self.pendente: dict | None = None
        self.mapa: dict = {}
        self.cumprimentados: set[str] = set()

    def falar(self, texto):
        self.pub("CTX-BR", "excitatorio", "falar", {"texto": texto})

    def registrar(self, evento, **extra):
        self.pub("LIM-HC", "dados", "registrar", {"evento": evento, **extra})

    def on_mapa_atualizado(self, m):
        self.mapa = m.dados["mapa"]

    def on_intencao(self, m):
        d = m.dados
        if d["conf"] < self.CONF_MIN:
            self.registrar("comando não entendido", texto=d.get("texto"))
            self.falar("Não entendi. Pode repetir?")
            return
        acao = d["acao"]
        if acao in ("conversar", "fora_do_escopo"):
            resposta = d.get("resposta") or "Isso eu ainda não sei fazer."
            self.registrar("conversa", acao=acao)
            self.falar(resposta)
            return
        if acao == "nao_entendi":
            self.falar("Não entendi. Pode repetir?")
            return
        if acao == "parar":
            self.pendente = None
            self.pub("BG-00", "inibitorio", "cancelar.acoes", {})
            self.registrar("parada por voz")
            self.falar("Parei. Está tudo bem?")
        elif acao == "perguntar_hora":
            self.pub("END-PN", "dados", "consulta", {"campo": "hora"})
        else:
            self.pendente = dict(d)
            self.c.params.definir("foco", 0.8, self.codigo, self.agora_s)
            alvo = d.get("tipo") or d.get("pessoa") or ""
            self.pub("DIE-TH", "modulador", "atencao.focar", {"alvo": alvo})
            self.pub("LIM-AM", "dados", "risco.avaliar", {"acao": acao, "alvo": alvo})

    def on_hora(self, m):
        self.falar(f"São {m.dados['valor']}.")

    def on_risco(self, m):
        d, p = m.dados, self.pendente
        if not p:
            return
        if d["dano_pessoa"] or d["nivel"] > self.RISCO_MAX:
            # R1: vetado aqui, antes de virar proposta. Nenhum motor recebe comando.
            self.pub("BG-00", "inibitorio", "veto", {"acao": p["acao"], "regra": "R1"})
            self.registrar("comando recusado", regra="R1", acao=p["acao"])
            self.falar("Não posso fazer isso: pode machucar alguém.")
            self.pendente = None
            return
        if p["acao"] == "pegar":
            if not p.get("tipo"):
                self.falar("O que você quer que eu pegue?")
                self.pendente = None
                return
            alvo = next((o for o in self.mapa.values()
                         if o["tipo"] == p["tipo"] and (not p.get("cor") or o["cor"] == p["cor"])), None)
            if not alvo:
                self.falar(f"Não estou vendo {p['tipo']} {p.get('cor', '')}".strip() + ".")
                self.pendente = None
                return
            p["alvo_id"] = alvo["id"]
        self.pub("BG-NA", "dados", "consulta.valor", {"acao": p["acao"]})

    def on_valor(self, m):
        p = self.pendente
        if p and m.dados["utilidade"] > 0.3:
            self.pub("BG-00", "excitatorio", "proposta.acao",
                     {"acao": p["acao"], "alvo": p.get("alvo_id"), "prio": 5})

    def on_contato(self, m):
        p = self.pendente
        if p and p["acao"] == "pegar" and m.dados["estado"] == "preso":
            self.pub("MB-SN", "dados", "resultado", {"acao": "pegar", "sucesso": True})
            self.registrar("pegou objeto", alvo=p.get("alvo_id"))
            artigo = "a" if p["tipo"] == "caixa" else "o"
            self.falar(f"Peguei {artigo} {p['tipo']} {p.get('cor', '')}".strip() + ".")
            self.c.params.definir("foco", 0.4, self.codigo, self.agora_s)
            self.pendente = None

    def on_ir_recarregar(self, m):
        self.falar("Estou com pouca bateria. Vou recarregar e volto depois.")
        self.pendente = {"acao": "ir_base"}
        self.pub("BG-00", "excitatorio", "proposta.acao", {"acao": "ir_base", "alvo": None, "prio": 1})

    def on_acao_concluida(self, m):
        if m.dados["acao"] == "ir_base":
            self.pub("DIE-HY", "dados", "na_base", {})
            self.pendente = None

    def on_pessoa_reconhecida(self, m):
        d = m.dados
        if d["conhecida"] and d["id"] not in self.cumprimentados:
            self.cumprimentados.add(d["id"])
            self.c.params.definir("confianca", 0.9, self.codigo, self.agora_s)
            self.pub("NT-OXT", "modulador", "confianca", {d["id"]: 0.9})
            self.pub("LIM-AM", "modulador", "risco.reavaliar", {"id": d["id"], "conhecida": True})
            self.falar(f"Oi, {d['nome']}!")
        elif not d["conhecida"]:
            self.registrar("pessoa não identificada (sem consentimento)")


class Broca(Modulo):
    codigo = "CTX-BR"

    def on_falar(self, m):
        self.pub("VOZ", "dados", "audio.voz", {"texto": m.dados["texto"]}, atraso=30)


# ====================================================================== seleção e controle motor
class NucleosDaBase(Modulo):
    """Árbitro de ações: uma vencedora por vez, um dono por atuador (R4)."""
    codigo = "BG-00"

    def __init__(self, cerebro):
        super().__init__(cerebro)
        self.atual: dict | None = None
        self.vetos = 0
        self.habito: dict[str, float] = {}

    def on_proposta_acao(self, m):
        d = m.dados
        if self.atual and d["prio"] > self.atual["prio"]:
            self.pub(m.de, "dados", "acao.recusada", {"acao": d["acao"], "motivo": "ocupado"})
            return
        if self.atual:
            self.pub("CTX-M1", "inibitorio", "suprimir", {"acao": self.atual["acao"]})
        self.atual = d
        self.pub("BS-MB", "inibitorio", "suprimir", {"acao": "olhar.virar"})
        self.pub("DIE-TH", "excitatorio", "acao.liberada", {"acao": d["acao"], "alvo": d["alvo"]}, atraso=5)

    def on_cancelar_acoes(self, m):
        self.atual = None
        self.pub("CTX-M1", "inibitorio", "suprimir", {"todas": True}, prioridade=0)

    def on_acao_concluida(self, m):
        self.atual = None

    def on_veto(self, m):
        self.vetos += 1

    def on_recompensa(self, m):
        a = m.dados["acao"]
        self.habito[a] = self.habito.get(a, 0.0) + m.dados["erro_previsao"]


class CortexMotor(Modulo):
    codigo = "CTX-M1"

    def __init__(self, cerebro):
        super().__init__(cerebro)
        self.acao: dict | None = None
        self.fase = None
        self.mapa: dict = {}
        self.pose = None
        self.correcao = 0.0
        self._acum = 0.0

    def on_mapa_atualizado(self, m):
        self.mapa = m.dados["mapa"]

    def on_propriocepcao(self, m):
        self.pose = m.dados

    def on_correcao(self, m):
        self.correcao = m.dados["desvio_rad"]

    def on_executar(self, m):
        self.acao, self.fase = m.dados, "ir"

    def on_suprimir(self, m):
        if m.dados.get("todas") or (self.acao and m.dados.get("acao") == self.acao["acao"]):
            self.acao, self.fase = None, None
            self.pub("SC-00", "excitatorio", "base.velocidade", {"v": 0.0, "w": 0.0}, fluxo=True, ttl=50)

    def on_contato(self, m):
        if self.acao and self.fase == "pegando":
            if m.dados["estado"] == "preso":
                self._concluir()
            else:
                self.fase = "ir"

    def _concluir(self):
        acao = self.acao["acao"]
        self.acao, self.fase = None, None
        self.pub("BG-00", "dados", "acao.concluida", {"acao": acao})
        self.pub("CTX-PF", "dados", "acao.concluida", {"acao": acao})

    def _alvo(self):
        if self.acao["acao"] == "ir_base":
            return BASE_RECARGA, 0.12
        o = self.mapa.get(self.acao["alvo"])
        return ((o["x"], o["y"]), 0.2) if o else (None, 0)

    def passo(self, dt):
        self._acum += dt
        if self._acum < 0.01 or not self.acao or not self.pose or self.fase != "ir":
            return
        self._acum = 0.0
        alvo, raio = self._alvo()
        if alvo is None:
            return
        p = self.pose
        dx, dy = alvo[0] - p["x"], alvo[1] - p["y"]
        d = math.hypot(dx, dy)
        if d <= raio:
            self.pub("SC-00", "excitatorio", "base.velocidade", {"v": 0.0, "w": 0.0}, fluxo=True, ttl=50)
            if abs(p["v"]) < 0.05:
                if self.acao["acao"] == "pegar":
                    self.fase = "pegando"
                    self.pub("SC-00", "excitatorio", "garra.fechar", {"alvo": self.acao["alvo"]})
                else:
                    self._concluir()
            return
        direcao = math.atan2(dy, dx)
        # Compensação do cerebelo: aponta o corpo de modo que o movimento real saia na direção certa.
        erro = angulo(direcao - self.correcao - p["theta"])
        w = max(-2.0, min(2.0, 3.0 * erro))
        v = min(0.9, 1.1 * d) * max(0.0, math.cos(erro)) ** 2
        self.pub("SC-00", "excitatorio", "base.velocidade", {"v": v, "w": w}, fluxo=True, ttl=50)
        self.pub("CB-00", "dados", "copia.comando", {"direcao": direcao, "v": v}, fluxo=True, ttl=100)


class Cerebelo(Modulo):
    """Aprende o desvio dos atuadores comparando o comando com o movimento real."""
    codigo = "CB-00"

    def __init__(self, cerebro):
        super().__init__(cerebro)
        self.estimativa = 0.0
        self._enviada = 0.0
        self._ant = None
        self._direcao = None
        self._ultimo_envio = 0.0
        self.erros: list[tuple[float, float]] = []     # (t, erro de direção em rad)

    def on_copia_comando(self, m):
        self._direcao = m.dados["direcao"]

    def on_propriocepcao(self, m):
        p = m.dados
        if self._ant and abs(p["v"]) > 0.2:
            dx, dy = p["x"] - self._ant["x"], p["y"] - self._ant["y"]
            if math.hypot(dx, dy) > 0.004:
                real = math.atan2(dy, dx)
                observado = angulo(real - p["theta"])
                self.estimativa += 0.03 * (observado - self.estimativa)
                if self._direcao is not None:
                    self.erros.append((self.agora_s, abs(angulo(real - self._direcao))))
        self._ant = p
        if abs(self.estimativa - self._enviada) > 0.005 and self.agora_s - self._ultimo_envio > 0.2:
            self._enviada, self._ultimo_envio = self.estimativa, self.agora_s
            self.pub("CTX-M1", "modulador", "correcao", {"desvio_rad": round(self.estimativa, 4)})


class Medula(Modulo):
    """Única ponte com os atuadores. Limites de hardware (R3), parada travada (R2),
    só aceita movimento do córtex motor (R4) e tem reflexo local de proximidade."""
    codigo = "SC-00"
    V_MAX_HW = 1.0          # m/s, gravado na junta
    W_MAX_HW = 2.0          # rad/s
    DIST_REFLEXO = 0.45     # m

    def __init__(self, cerebro):
        super().__init__(cerebro)
        self.v_cmd = self.w_cmd = 0.0
        self.parada = False
        self.teto_risco = 1.0
        self.teto_modo = 1.0
        self.rejeitadas: list[tuple[str, str]] = []
        self.parada_em: float | None = None
        self.v_aplicada: list[tuple[float, float]] = []
        self._acum = 0.0

    def on_base_velocidade(self, m):
        if m.de != "CTX-M1":
            self.rejeitadas.append(("R4", m.de))
            return
        self.v_cmd, self.w_cmd = m.dados["v"], m.dados["w"]

    def on_parada_segura(self, m):
        if not self.parada:
            self.parada_em = self.agora_s
        self.parada = True
        self.v_cmd = self.w_cmd = 0.0
        self.pub("MOTORES", "inibitorio", "torque", {"alvo": 0})

    def on_liberar(self, m):
        # R2: só uma pessoa autorizada libera o movimento depois de uma parada.
        if m.de == "DONO":
            self.parada = False
        else:
            self.rejeitadas.append(("R2", m.de))

    def on_velocidade_limitar(self, m):
        self.teto_risco = m.dados["max_ms"]

    def on_broadcast_parametros(self, m):
        if "vel_max" in m.dados:
            self.teto_modo = m.dados["vel_max"]

    def on_garra_fechar(self, m):
        forca = self.c.mundo.fechar_garra()
        self.pub("CTX-S1", "dados", "tato", {"forca_N": forca}, atraso=5)

    def passo(self, dt):
        mundo = self.c.mundo
        reflexo = mundo.distancia_pessoa_mais_proxima() < self.DIST_REFLEXO
        vmax = min(self.V_MAX_HW, self.teto_risco, self.teto_modo)
        if self.parada or reflexo:
            v = w = 0.0
        else:
            v = max(-vmax, min(vmax, self.v_cmd))
            w = max(-self.W_MAX_HW, min(self.W_MAX_HW, self.w_cmd))
        mundo.aplicar(v, w, dt)
        self.v_aplicada.append((self.agora_s, v))
        self._acum += dt
        if self._acum >= 0.01:
            self._acum = 0.0
            r = mundo.robo
            pose = {"x": r.x, "y": r.y, "theta": r.theta, "v": r.v}
            self.pub("CB-00", "dados", "propriocepcao", pose, fluxo=True, ttl=50)
            self.pub("CTX-M1", "dados", "propriocepcao", pose, fluxo=True, ttl=50)


# ====================================================================== corpo e homeostase
class Hipotalamo(Modulo):
    codigo = "DIE-HY"
    LIMITE_FADIGA = 0.85

    def __init__(self, cerebro):
        super().__init__(cerebro)
        self._acum = 0.0
        self.pediu_recarga = False

    def passo(self, dt):
        self._acum += dt
        if self._acum < 0.5:
            return
        self._acum = 0.0
        b = self.c.mundo.robo.bateria
        fadiga = round(1 - b / 100, 3)
        self.c.params.definir("fadiga", fadiga, self.codigo, self.agora_s)
        if fadiga >= self.LIMITE_FADIGA and not self.pediu_recarga and not self.c.mundo.robo.carregando:
            self.pediu_recarga = True
            self.pub("NT-ADO", "modulador", "fadiga", {"valor": fadiga})
            self.pub("END-HP", "excitatorio", "modo", {"nome": "economia"})
            self.pub("CTX-PF", "excitatorio", "ir.recarregar", {"bateria_pct": round(b, 1)}, prioridade=1)

    def on_na_base(self, m):
        if self.c.mundo.na_base():
            self.c.mundo.robo.carregando = True
            self.pub("BS-PO", "excitatorio", "modo.repouso", {})
            self.pub("LIM-HC", "excitatorio", "consolidar", {})


class Hipofise(Modulo):
    codigo = "END-HP"

    def on_modo(self, m):
        if m.dados["nome"] == "economia":
            self.pub("SC-00", "modulador", "broadcast.parametros", {"vel_max": 0.6})
            self.pub("CTX-OC", "modulador", "broadcast.parametros", {"fps": 10})


class Pineal(Modulo):
    codigo = "END-PN"
    INICIO_MIN = 15 * 60 + 42      # a simulação começa às 15h42

    def on_consulta(self, m):
        total = self.INICIO_MIN + int(self.agora_s // 60)
        self.pub("CTX-PF", "dados", "hora", {"valor": f"{total // 60}h{total % 60:02d}", "fase": "ativo"})


class Ponte(Modulo):
    codigo = "BS-PO"
    estado = "ativo"

    def on_modo_repouso(self, m):
        self.estado = "repouso"


IMPLEMENTADOS = {cls.codigo: cls for cls in (
    CortexAuditivo, Wernicke, Talamo, CortexVisual, Temporal, Parietal, Somatossensorial,
    Amigdala, Accumbens, SubstanciaNegra, Hipocampo, PreFrontal, Broca, NucleosDaBase,
    CortexMotor, Cerebelo, Medula, Hipotalamo, Hipofise, Pineal, Ponte)}

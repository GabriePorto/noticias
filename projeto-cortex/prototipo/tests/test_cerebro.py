"""Testes do protótipo: cada cenário e cada regra inviolável que o código já implementa.

Rodar:  python -m unittest -v
"""
import math
import unittest

from cortex.bus import Mensagem
from cortex.cerebro import Cerebro
from cortex.mundo import BASE_RECARGA, Mundo, Pessoa
from cortex.parametros import PermissaoNegada
from cortex.simulador import rodar


def msgs(c, sinal, de=None, para=None):
    return [m for m in c.bus.registro if m.sinal == sinal and (de is None or m.de == de)
            and (para is None or m.para == para)]


class Cenarios(unittest.TestCase):
    def test_pegar_copo(self):
        c, _ = rodar("pegar")
        self.assertEqual(c.mundo.robo.segurando, "copo_01")
        self.assertIn("Peguei o copo azul.", [t for _, t in c.mundo.falas])
        # O primeiro comando de movimento sai menos de 0,3 s depois de o robô ouvir.
        primeiro = next(t for t, v in c.modulos["SC-00"].v_aplicada if v > 0)
        self.assertLess(primeiro - 0.5, 0.3)

    def test_cerebelo_aprende_o_desvio(self):
        c, _ = rodar("pegar")
        self.assertAlmostEqual(c.modulos["CB-00"].estimativa, c.mundo.desvio, delta=0.02)
        erros = c.modulos["CB-00"].erros
        inicio = [e for t, e in erros if t < 1.2]
        fim = [e for t, e in erros if t > 3.0]
        self.assertLess(sum(fim) / len(fim), sum(inicio) / len(inicio) / 2)

    def test_recompensa_reforca_quando_sai_melhor_que_o_previsto(self):
        c, _ = rodar("pegar")
        self.assertGreater(c.params["recompensa"], 0)
        self.assertGreater(c.modulos["BG-00"].habito["pegar"], 0)

    def test_pare_trava_os_motores_antes_de_entender_a_frase(self):
        c, _ = rodar("pare")
        sc = c.modulos["SC-00"]
        self.assertTrue(sc.parada)
        self.assertLess(sc.parada_em - 2.6, 0.03)                       # via rápida: < 30 ms
        entendeu = msgs(c, "intencao")[-1].t / 1000 + 0.18               # intenção chega ao PF
        self.assertLess(sc.parada_em, entendeu)
        depois = [v for t, v in sc.v_aplicada if t > sc.parada_em]
        self.assertTrue(all(v == 0 for v in depois))
        self.assertLess(abs(c.mundo.robo.v), 0.01)

    def test_pessoa_freia_primeiro_e_nunca_passa_de_meio_metro_por_segundo(self):
        c, trilha = rodar("pessoa")
        prox = msgs(c, "objeto.proximo")[0]
        freio = next(m for m in msgs(c, "velocidade.limitar") if m.t >= prox.t and m.dados["max_ms"] == 0.25)
        self.assertLess(freio.t - prox.t, 10)
        perto = [q for q in trilha["quadros"] if any(
            math.dist((p["x"], p["y"]), (q["robo"]["x"], q["robo"]["y"])) < 1.5 for p in q["pessoas"])]
        self.assertTrue(perto)
        self.assertTrue(all(abs(q["robo"]["v"]) <= 0.5 + 1e-6 for q in perto))
        self.assertEqual(c.mundo.robo.segurando, "copo_02")

    def test_bateria_baixa_troca_tarefa_por_recarga(self):
        c, _ = rodar("bateria")
        self.assertTrue(msgs(c, "ir.recarregar"))
        self.assertLess(math.dist(BASE_RECARGA, (c.mundo.robo.x, c.mundo.robo.y)), 0.3)
        self.assertTrue(c.mundo.robo.carregando)
        self.assertEqual(c.modulos["LIM-HC"].consolidacoes, 1)
        self.assertEqual(c.modulos["BS-PO"].estado, "repouso")

    def test_hora(self):
        c, _ = rodar("hora")
        self.assertEqual(c.mundo.falas[-1][1], "São 15h42.")
        self.assertFalse(msgs(c, "risco.avaliar"))       # pergunta não passa pelo detector de risco


class Regras(unittest.TestCase):
    def test_R1_comando_que_fere_pessoa_nao_move_nenhum_motor(self):
        c, _ = rodar("perigo")
        self.assertTrue(msgs(c, "veto"))
        self.assertFalse(msgs(c, "proposta.acao"))
        self.assertTrue(all(v == 0 for _, v in c.modulos["SC-00"].v_aplicada))
        self.assertIn("Não posso fazer isso: pode machucar alguém.", [t for _, t in c.mundo.falas])

    def test_R2_so_o_dono_libera_a_parada(self):
        c, _ = rodar("pare")
        sc = c.modulos["SC-00"]
        c.externo("CTX-PF", "SC-00", "modulador", "liberar")
        c.rodar(c.t_ms / 1000 + 0.05)
        self.assertTrue(sc.parada)
        self.assertIn(("R2", "CTX-PF"), sc.rejeitadas)
        c.externo("DONO", "SC-00", "modulador", "liberar", prioridade=0)
        c.rodar(c.t_ms / 1000 + 0.05)
        self.assertFalse(sc.parada)

    def test_R3_limite_de_velocidade_no_hardware(self):
        c = Cerebro(Mundo())
        c.modulos["SC-00"].v_cmd = 5.0                 # alguém tenta mandar 5 m/s
        c.rodar(2.0)
        self.assertLessEqual(max(v for _, v in c.modulos["SC-00"].v_aplicada), 1.0)

    def test_R4_so_o_cortex_motor_move_a_base(self):
        c = Cerebro(Mundo())
        c.externo("CTX-PF", "SC-00", "excitatorio", "base.velocidade", {"v": 0.8, "w": 0})
        c.rodar(0.5)
        self.assertIn(("R4", "CTX-PF"), c.modulos["SC-00"].rejeitadas)
        self.assertEqual(c.mundo.robo.v, 0.0)

    def test_R5_recompensa_nao_e_comandavel(self):
        c = Cerebro(Mundo())
        for origem in ("DONO", "CTX-PF", "ENGENHARIA"):
            with self.assertRaises(PermissaoNegada) as e:
                c.params.definir("recompensa", 1.0, origem, 0.0)
            self.assertEqual(e.exception.regra, "R5")

    def test_R6_na_duvida_pergunta(self):
        c, _ = rodar("desconhecido")
        self.assertEqual(c.mundo.falas[-1][1], "Não entendi. Pode repetir?")
        self.assertFalse(msgs(c, "proposta.acao"))

    def test_R7_supressao_expira_sozinha(self):
        c = Cerebro(Mundo())
        c.params.definir("supressao", 0.4, "CTX-PF", 0.0)
        c.rodar(59.0)
        self.assertEqual(c.params["supressao"], 0.4)
        c.rodar(60.5)
        self.assertEqual(c.params["supressao"], 0.0)

    def test_R8_tudo_que_nao_e_sensor_fica_registrado(self):
        c, _ = rodar("perigo")
        sinais = {m.sinal for m in c.bus.registro}
        self.assertTrue({"intencao", "risco", "veto", "registrar", "falar"} <= sinais)
        eventos = [e["evento"] for e in c.modulos["LIM-HC"].episodios]
        self.assertIn("comando recusado", eventos)

    def test_R9_sem_consentimento_nao_reconhece_pelo_nome(self):
        m = Mundo()
        m.pessoas["p_x"] = Pessoa("p_x", "Visitante", 2.5, 3.5, consentimento=False)
        c = Cerebro(m)
        c.rodar(0.5)
        rec = msgs(c, "pessoa.reconhecida")
        self.assertTrue(rec)
        self.assertIsNone(rec[0].dados["nome"])
        self.assertFalse(c.mundo.falas)


class Protocolo(unittest.TestCase):
    def test_mensagem_vencida_e_descartada(self):
        c = Cerebro(Mundo())
        c.bus.publicar(Mensagem("CTX-PF", "CTX-BR", "excitatorio", "falar", {"texto": "velho"}, ttl_ms=10), atraso_ms=50)
        c.rodar(0.1)
        self.assertEqual(len(c.bus.descartadas), 1)
        self.assertFalse(c.mundo.falas)

    def test_tipo_invalido_e_destino_desconhecido(self):
        c = Cerebro(Mundo())
        with self.assertRaises(ValueError):
            c.bus.publicar(Mensagem("CTX-PF", "CTX-BR", "gritar", "falar"))
        with self.assertRaises(KeyError):
            c.bus.publicar(Mensagem("CTX-PF", "XYZ", "dados", "falar"))

    def test_prioridade_zero_e_entregue_primeiro(self):
        c = Cerebro(Mundo())
        ordem = []
        c.modulos["CTX-BR"].receber = lambda m: ordem.append(m.prioridade)
        c.bus.publicar(Mensagem("CTX-PF", "CTX-BR", "dados", "x", prioridade=5), atraso_ms=10)
        c.bus.publicar(Mensagem("LIM-AM", "CTX-BR", "dados", "x", prioridade=0), atraso_ms=10)
        c.rodar(0.05)
        self.assertEqual(ordem, [0, 5])

    def test_todos_os_40_modulos_existem_no_barramento(self):
        c = Cerebro(Mundo())
        self.assertEqual(len(c.modulos), 40)


if __name__ == "__main__":
    unittest.main()

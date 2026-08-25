#!/usr/bin/env python3
"""
transcrever.py — Transcreve vídeos do YouTube (e outros sites) usando as
legendas nativas, gerando um texto limpo com timestamps.

Uso:
    python3 transcrever.py <URL> [-l pt] [-o saida.txt]

Exemplos:
    python3 transcrever.py "https://youtu.be/qjUeeBwJvS8"
    python3 transcrever.py "https://youtu.be/qjUeeBwJvS8" -l en -o transcricao.txt

Requisitos:
    - yt-dlp   (pip install yt-dlp)

Como funciona:
    1. Baixa as legendas (manuais ou automáticas) via yt-dlp.
    2. Faz o parse do formato VTT e remove as repetições típicas das
       legendas automáticas (que sobem linha a linha).
    3. Salva um .txt limpo, com timestamp [mm:ss] no começo de cada fala.

Observação: legendas automáticas podem ter pequenos erros de reconhecimento
(nomes próprios, marcas etc.). O texto reflete o que o YouTube reconheceu.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile


def sh(cmd):
    """Roda um comando e devolve (returncode, stdout, stderr)."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def checar_ytdlp():
    if sh(["yt-dlp", "--version"])[0] != 0:
        sys.exit("ERRO: yt-dlp não encontrado. Instale com:  pip install yt-dlp")


def pegar_metadados(url):
    """Título, autor e duração. Retorna dict (campos podem faltar)."""
    rc, out, _ = sh([
        "yt-dlp", "--skip-download", "--no-warnings",
        "--extractor-args", "youtube:player_client=android,ios",
        "--print", "%(title)s\t%(uploader)s\t%(duration_string)s",
        url,
    ])
    if rc == 0 and out.strip():
        partes = out.strip().splitlines()[-1].split("\t")
        partes += [""] * (3 - len(partes))
        return {"titulo": partes[0], "autor": partes[1], "duracao": partes[2]}
    return {"titulo": "", "autor": "", "duracao": ""}


def baixar_legendas(url, lang, workdir):
    """
    Baixa legendas (manuais e automáticas) no idioma pedido.
    Retorna o caminho do .vtt escolhido, ou None.
    """
    alvo = os.path.join(workdir, "sub")
    # player_client=android,ios costuma contornar o bloqueio de bot / erro 429.
    sh([
        "yt-dlp", "--skip-download", "--no-warnings",
        "--write-sub", "--write-auto-sub",
        "--sub-langs", f"{lang}.*,{lang}",
        "--sub-format", "vtt",
        "--extractor-args", "youtube:player_client=android,ios,tv",
        "-o", alvo + ".%(ext)s",
        url,
    ])
    vtts = [os.path.join(workdir, f) for f in os.listdir(workdir)
            if f.endswith(".vtt")]
    if not vtts:
        return None
    # Prefere legenda manual (sem "-orig"/"auto") no idioma exato, se houver.
    def score(path):
        nome = os.path.basename(path).lower()
        s = 0
        if f".{lang}." in nome and "orig" not in nome:
            s += 2
        if "auto" not in nome:
            s += 1
        return s
    vtts.sort(key=score, reverse=True)
    return vtts[0]


def parse_vtt(path):
    """Extrai pares (timestamp, texto) de um arquivo VTT."""
    linhas = open(path, encoding="utf-8").read().splitlines()
    tsre = re.compile(r"(\d{2}:\d{2}:\d{2})\.\d{3}\s+-->")
    entradas = []
    for idx, ln in enumerate(linhas):
        m = tsre.search(ln)
        if not m:
            continue
        ts = m.group(1)
        texto = []
        j = idx + 1
        while j < len(linhas) and linhas[j].strip():
            limpo = re.sub(r"<[^>]+>", "", linhas[j]).strip()  # tira tags de timing
            if limpo:
                texto.append(limpo)
            j += 1
        if texto:
            entradas.append((ts, " ".join(texto)))
    return entradas


def limpar(entradas):
    """Remove repetições consecutivas e marcadores de som ([música] etc.)."""
    saida = []
    anterior = None
    for ts, txt in entradas:
        txt = re.sub(r"\[[^\]]*\]", " ", txt)          # [música], [aplausos]...
        txt = re.sub(r"\s+", " ", txt).strip()
        if not txt or txt == anterior:
            continue
        saida.append((ts[3:], txt))  # descarta a parte de horas -> mm:ss
        anterior = txt
    return saida


def main():
    ap = argparse.ArgumentParser(
        description="Transcreve vídeos usando legendas nativas do YouTube.")
    ap.add_argument("url", help="URL do vídeo")
    ap.add_argument("-l", "--lang", default="pt",
                    help="Idioma da legenda (padrão: pt)")
    ap.add_argument("-o", "--out", default=None,
                    help="Arquivo de saída (padrão: transcricao-<id>.txt)")
    args = ap.parse_args()

    checar_ytdlp()

    with tempfile.TemporaryDirectory() as workdir:
        print("• Buscando metadados...", file=sys.stderr)
        meta = pegar_metadados(args.url)

        print(f"• Baixando legendas ({args.lang})...", file=sys.stderr)
        vtt = baixar_legendas(args.url, args.lang, workdir)
        if not vtt:
            sys.exit(f"ERRO: nenhuma legenda '{args.lang}' encontrada para esse vídeo.\n"
                     f"Tente outro idioma com -l (ex.: -l en).")

        falas = limpar(parse_vtt(vtt))
        if not falas:
            sys.exit("ERRO: legenda encontrada, mas sem texto legível.")

    # Nome de saída
    saida = args.out
    if not saida:
        vid = re.search(r"(?:v=|/)([\w-]{11})(?:[?&]|$)", args.url)
        vid = vid.group(1) if vid else "video"
        saida = f"transcricao-{vid}.txt"

    with open(saida, "w", encoding="utf-8") as f:
        if meta["titulo"]:
            f.write(f"{meta['titulo']}\n")
        linha_info = " · ".join(x for x in [meta["autor"], meta["duracao"]] if x)
        if linha_info:
            f.write(f"{linha_info}\n")
        f.write(f"{args.url}\n")
        f.write("Fonte: legendas do YouTube (podem conter erros de reconhecimento)\n")
        f.write("=" * 60 + "\n\n")
        for ts, txt in falas:
            f.write(f"[{ts}] {txt}\n")

    print(f"✓ Transcrição salva em: {saida}  ({len(falas)} linhas)", file=sys.stderr)


if __name__ == "__main__":
    main()

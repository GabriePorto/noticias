# Ferramenta de Transcrição

Script simples para transcrever vídeos do YouTube (e outros sites suportados
pelo yt-dlp) usando as **legendas nativas**, gerando um `.txt` limpo com
timestamps.

## Instalação

```bash
pip install yt-dlp
```

## Uso

```bash
python3 transcrever.py "<URL>"
```

### Opções

| Flag           | Descrição                                  | Padrão                     |
|----------------|--------------------------------------------|----------------------------|
| `-l`, `--lang` | Idioma da legenda (`pt`, `en`, `es`, ...)  | `pt`                       |
| `-o`, `--out`  | Arquivo de saída                           | `transcricao-<id>.txt`     |

### Exemplos

```bash
# Transcrição em português
python3 transcrever.py "https://youtu.be/qjUeeBwJvS8"

# Em inglês, salvando com nome específico
python3 transcrever.py "https://youtu.be/qjUeeBwJvS8" -l en -o aula.txt
```

## O que ele faz

1. Baixa as legendas (manuais ou automáticas) via `yt-dlp`.
2. Faz o parse do formato VTT e remove as repetições típicas das legendas
   automáticas (que sobem linha a linha) e marcadores como `[música]`.
3. Salva um `.txt` com cabeçalho (título, autor, duração) e cada fala
   prefixada por `[mm:ss]`.

## Observações

- Legendas **automáticas** podem conter pequenos erros de reconhecimento
  (nomes próprios, marcas etc.). O texto reflete o que o YouTube reconheceu.
- Se o vídeo não tiver legenda no idioma pedido, o script avisa — tente outro
  idioma com `-l`.
- Em ambientes de nuvem o YouTube às vezes exige verificação de robô; o script
  já usa os clientes `android/ios` do yt-dlp, que costumam contornar isso.

# Posts 7 de Setembro — Independência do Brasil (2026)

Dois posts em formato **1080x1920** (stories / reels cover), um por marca.

| Marca | Arquivo final | Fonte |
|---|---|---|
| Stetikos Hospital | `post_stetikos_7set_1080x1920.png` | `stetikos.html` |
| AutoCar Auto Peças | `post_autocar_7set_1080x1920.png` | `autocar.html` |

## Paletas usadas

**Stetikos Hospital** (extraída dos materiais da marca no Canva)
- Verde petróleo `#00594C` / `#00786A`
- Coral `#F2795A` (secundária, tipografia de apoio)
- Off-white `#F7F5F2`
- Apoio: `#CDE9E3`

**AutoCar Auto Peças** (extraída do flyer de inauguração AutoCar BH)
- Azul marinho `#0A1A3C` / `#061029`
- Azul royal `#1B4FA0` / `#2E6FD4`
- Grafite `#171A21`
- Branco `#FFFFFF`

Acento nacional (verde `#0E9B62`, amarelo `#F5C518`, azul) aplicado só em detalhes,
sem competir com a identidade de cada marca.

## Como regerar

```sh
chrome --headless --no-sandbox --hide-scrollbars \
  --window-size=1080,2007 --screenshot=out.png file://$PWD/stetikos.html
# depois cortar para 1080x1920 (o viewport do headless fica 87px menor que a window)
```

Fontes: Poppins e Saira Condensed (Google Fonts), referenciadas em `fonts.css`
por caminho local — ajuste os caminhos ao regerar em outra máquina.

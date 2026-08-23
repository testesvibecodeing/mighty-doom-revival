# Entrada local para o fundo da RevivalAuthActivity

Este diretório é **ignorado pelo git** (`.gitignore` — regra 1 do `AGENTS.md`:
nunca commitar imagem/material proprietário). Só este `README.md` é versionado.

Para dar um fundo à tela de login, coloque aqui um PNG e passe o caminho para
`scripts/revival_auth/build.py` via `background_png=` (`build_dex()` /
`render_source()`) ou `scripts/patch_revival_auth.py --background-png`.

Sem nada aqui, a Activity compila e roda normalmente com o fundo sólido
(`#0B0604`) definido em código — a tela nunca depende da imagem para
funcionar.

O arquivo nunca entra no `.dex`/APK como recurso separado: `build.py` lê os
bytes, codifica em base64 e embute como constante de string no `.java` gerado
em tempo de build (a fonte rastreada no git tem só um marcador
`@@REVIVAL_BG_B64_ENTRIES@@`, nunca o binário).

Limite: 2 MiB (`BG_MAX_BYTES` em `build.py`) — o fundo é cosmético, não vale
inflar o dex.

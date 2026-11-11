
# ================================
# 1️⃣ Instalar OpenCode V2
# ================================
!curl -fsSL https://opencode.ai/v2/install | bash

# ================================
# 2️⃣ Ajustar PATH
# ================================
import os

os.environ["PATH"] = "/root/.opencode/bin:" + os.environ["PATH"]

# ================================
# 3️⃣ Verificar instalação
# ================================
OPENCODE = "/root/.opencode/bin/opencode"

!{OPENCODE} --version

# ================================
# 4️⃣ Fazer pergunta
# ================================
pergunta = """
BAIXE github.com/tcsenpai/audiocoqui
E TRANSFORME /content/drive/MyDrive/baixe do YouTube/fd907e5e-cdd7-4b0f-9ed5-b40ae96851b8_cópia.pdf
EM MP3 E SALVE NA MESMA PASTA
"""

print("Pergunta:", pergunta)
print("\nResposta do OpenCode:\n")

# ================================
# 5️⃣ Executar OpenCode V2
# ================================
!{OPENCODE} run "{pergunta}"

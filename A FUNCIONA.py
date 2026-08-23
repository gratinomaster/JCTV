 
# ================================
# 1️⃣ Instalar OpenCode
# ================================
!curl -fsSL https://opencode.ai/install | bash

# ================================
# 2️⃣ Ajustar PATH (Colab não carrega .bashrc automaticamente)
# ================================
import os
os.environ["PATH"] = "/root/.opencode/bin:" + os.environ["PATH"]

# ================================
# 3️⃣ Verificar instalação
# ================================
!opencode --version

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

!opencode run "{pergunta}"

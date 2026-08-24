 
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
BAIXE https://github.com/shinshekai/VoxForge-Pro
E TRANSFORME /content/drive/MyDrive/baixe do YouTube/Segredos da atração.pdf
EM MP3 E SALVE NA MESMA PASTA
o audio de referencia será algum em que o cid moreira fala, use uma amostra limpa de 1–5 min
deve ser baixado da internet
Mantenha a pronúncia em português brasileiro.
Busque uma narração fluida, clara e natural.
Respeite pontuação, parágrafos, títulos e pausas para que o resultado tenha características de audiobook.
"""

print("Pergunta:", pergunta)
print("\nResposta do OpenCode:\n")

!opencode run "{pergunta}"

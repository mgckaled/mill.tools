"""Gera os 2 arquivos .parquet de teste com erros propositais.

Rode no projeto (onde o uv tem pyarrow):  uv run python test_data/gerar_parquet.py
O sandbox da sessão não tem engine de Parquet, por isso este passo fica aqui.
"""
import os
import random
import pandas as pd

OUT = os.path.dirname(os.path.abspath(__file__))
random.seed(42)

produtos = ["Caneca", "Camiseta", "Caderno", "Mochila", "Garrafa", "Fone"]
status_opts = ["pago", "pendente", "estornado", "PAGO", None]

# ---------- transacoes.parquet ----------
trans = []
for i in range(1, 21):
    trans.append({
        "id_transacao": i,
        "data": random.choice(["2026-01-05", "2026-01-12", "2026-02-01"]),
        "valor": round(random.uniform(20, 500), 2),
        "status": random.choice(status_opts),
    })
trans[3]["valor"] = None        # nulo em coluna numérica
trans[6]["valor"] = -199.90     # valor negativo (erro)
trans.append(dict(trans[2]))    # transação duplicada
df1 = pd.DataFrame(trans)
df1.to_parquet(os.path.join(OUT, "transacoes.parquet"), index=False)

# ---------- estoque.parquet ----------
est = []
for i in range(1, 16):
    est.append({
        "sku": f"SKU-{1000 + i}",
        "produto": random.choice(produtos),
        "quantidade": random.randint(0, 300),
        "deposito": random.choice(["A", "B", "C", None]),
    })
est[2]["quantidade"] = -15       # estoque negativo (erro)
est[5]["quantidade"] = None      # nulo
est[8]["sku"] = est[0]["sku"]    # sku duplicado
df2 = pd.DataFrame(est)
df2.to_parquet(os.path.join(OUT, "estoque.parquet"), index=False)

print("OK - gerados: transacoes.parquet, estoque.parquet")

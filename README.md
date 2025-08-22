# Programação de Obras — v0.4

App web (Streamlit) para consulta do **número de programação** por Rodovia, Tipo, Data, Período, Sentido e Executor.
- Lê **bases** definidas no `bases.json` (SharePoint/OneDrive, link com `?download=1`).
- Concatena **semana_atual** + **proxima_semana**.
- Sidebar mostra **status** (somente leitura).

## Como usar
1. Suba este projeto no GitHub e aponte o Streamlit Cloud para `app.py`.
2. O app usa a URL do `bases.json` nesta ordem de prioridade:
   - `st.secrets["BASES_JSON_URL"]`
   - variável de ambiente `BASES_JSON_URL`
   - `config.json` com `{ "BASES_JSON_URL": "https://.../bases.json?download=1" }`
   - **fallback no código** (já configurado neste pacote).
3. Preencha todos os filtros e clique **Buscar**.

## Colunas obrigatórias
`Num Interv, Rodovia, Tipo, Inicio, DataFim, Sentido, Trecho, Executor`

## Observações
- Se o `bases.json` estiver inválido, o app mostra erro claro.
- Se apenas uma base estiver disponível, o app usa a que estiver ok e informa na sidebar.
- No Streamlit Cloud o diretório `data/` é efêmero; ao reiniciar, o app baixa novamente a partir do `bases.json`.

**Versão:** v0.4

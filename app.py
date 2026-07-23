"""
SIGALI — Sistema Inteligente de Gestão da Agenda Legislativa da Indústria
Versão auto-hospedada (Streamlit + Supabase)

Como rodar localmente:
    pip install -r requirements.txt
    streamlit run app.py

Configuração (arquivo .streamlit/secrets.toml ou "Secrets" no Streamlit Cloud):
    supabase_url = "https://SEU-PROJETO.supabase.co"
    supabase_key = "SUA_CHAVE_ANON_OU_SERVICE_ROLE"
    admin_pin = "sigali2027"
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
from supabase import create_client

st.set_page_config(page_title="SIGALI", page_icon="🏛️", layout="wide")

st.markdown(
    """<style>
    table thead tr th:first-child {display:none}
    table tbody th {display:none}
    </style>""",
    unsafe_allow_html=True,
)

MACROETAPAS = ["Cerimônia", "Encontro", "Lançamento", "Publicação", "Quem é Quem", "Seminário", "Transversal", "Outra"]
TIPOS_DEMANDA = ["Apresentação", "Briefing", "Evento", "Interação", "Outros", "Reunião", "Outro"]
STATUS_OPCOES = ["Pendente", "Em elaboração", "Resolvida"]
STATUS_MARCO_OPCOES = ["Pendente", "Resolvido"]


@st.cache_resource
def get_client():
    return create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])


sb = get_client()


# ---------- Dados ----------

def carregar(tabela: str) -> pd.DataFrame:
    res = sb.table(tabela).select("*").execute()
    df = pd.DataFrame(res.data)
    for col in ("data_inicio", "data_prazo", "data_sugerida"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    if "ciclo" not in df.columns:
        df["ciclo"] = "ALI 2027"
    df["ciclo"] = df["ciclo"].fillna("ALI 2027")
    return df


def slugify(texto: str) -> str:
    import re
    import unicodedata
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-zA-Z0-9]+", "-", texto).strip("-").lower()
    return texto or "ciclo"


def parse_planilha_cronograma(bruto: pd.DataFrame, ciclo: str) -> list:
    """Lê uma planilha no mesmo formato da Matriz RACI - Cronograma e devolve uma lista de atividades prontas para importar."""
    bruto = bruto.copy()
    bruto.columns = [str(c).strip() for c in bruto.columns]
    prefixo = slugify(ciclo)

    def to_iso(x):
        if isinstance(x, (pd.Timestamp, datetime, date)):
            return str(pd.Timestamp(x).date())
        return None

    registros = []
    for _, row in bruto.iterrows():
        id_original = str(row.get("ID", "")).strip()
        titulo = row.get("Título da Atividade")
        if not isinstance(titulo, str) or not titulo.strip():
            continue
        inicio = to_iso(row.get("Início"))
        fim = to_iso(row.get("Fim"))
        prazo = fim or inicio
        descricao = row.get("Descrição da Atividade")
        descricao = descricao.strip() if isinstance(descricao, str) else ""
        observacoes = row.get("Observações")
        observacoes = observacoes.strip() if isinstance(observacoes, str) else ""
        responsavel = row.get("R (Executa)")
        responsavel = responsavel.strip() if isinstance(responsavel, str) else "A definir"
        sinalizado = str(row.get("Muniz", "")).strip().lower() == "sim"
        registros.append({
            "id": f"{prefixo}-{id_original}" if id_original else f"{prefixo}-{slugify(titulo)[:40]}",
            "nome": titulo.strip(),
            "descricao": descricao,
            "macroetapa": row.get("Subprocesso") if isinstance(row.get("Subprocesso"), str) else "Outra",
            "tipo_demanda": row.get("Tipo de Demanda") if isinstance(row.get("Tipo de Demanda"), str) else "Outro",
            "data_inicio": inicio,
            "data_prazo": prazo,
            "responsavel": responsavel,
            "status": "Pendente",
            "observacoes": observacoes,
            "sinalizado_diretor": sinalizado,
            "ciclo": ciclo,
        })
    return registros


def status_efetivo(row) -> str:
    if row.get("status") == "Resolvida":
        return "Resolvida"
    prazo = row.get("data_prazo")
    if prazo and isinstance(prazo, date) and prazo < date.today():
        return "Atrasada"
    return row.get("status") or "Pendente"


def eh_critica(row) -> bool:
    s = status_efetivo(row)
    if s == "Resolvida":
        return False
    if s == "Atrasada":
        return True
    prazo = row.get("data_prazo")
    if prazo and isinstance(prazo, date):
        d = (prazo - date.today()).days
        if 0 <= d <= 3:
            return True
    return False


def sincronizar(tabela: str, df_editado: pd.DataFrame, df_original: pd.DataFrame, chave: str = "id", ciclo_forcado: str = None):
    """Compara o dataframe editado no data_editor com o original e aplica insert/update/delete no Supabase."""
    ids_originais = set(df_original[chave]) if not df_original.empty else set()
    ids_editados = set(df_editado[chave].dropna())

    removidos = ids_originais - ids_editados
    for rid in removidos:
        sb.table(tabela).delete().eq(chave, rid).execute()

    for _, row in df_editado.iterrows():
        registro = row.to_dict()
        for k, v in list(registro.items()):
            if isinstance(v, (pd.Timestamp, date, datetime)):
                registro[k] = str(v)
            if pd.isna(v):
                registro[k] = None
        if not registro.get(chave):
            registro[chave] = f"{tabela[:1].upper()}{int(datetime.now().timestamp() * 1000) % 1000000}"
        if ciclo_forcado:
            registro["ciclo"] = ciclo_forcado
        sb.table(tabela).upsert(registro).execute()


# ---------- Login e navegação ----------

if "perfil" not in st.session_state:
    st.session_state.perfil = "colaborador"

PAGINAS = ["📊 Painel", "🗓️ Cronograma", "🚩 Muniz", "👥 Responsáveis"]

with st.sidebar:
    st.markdown("### 🏛️ SIGALI")
    st.caption("Confederação Nacional da Indústria · Distrito Federal")
    st.divider()
    pagina = st.radio("Menu", PAGINAS, label_visibility="collapsed")

is_admin = st.session_state.perfil == "admin"

etapas_todas = carregar("etapas")
responsaveis = carregar("responsaveis")
marcos_todos = carregar("marcos")

ciclos_disponiveis = sorted(etapas_todas["ciclo"].dropna().unique().tolist(), reverse=True)
with st.sidebar:
    st.divider()
    ciclo_selecionado = st.selectbox("Ciclo / Agenda", ciclos_disponiveis, index=0) if ciclos_disponiveis else None
    st.divider()
    if st.session_state.perfil == "admin":
        st.success("Modo: Administrador")
        if st.button("Sair do modo administrador"):
            st.session_state.perfil = "colaborador"
            st.rerun()
    else:
        st.info("Modo: Colaborador (somente leitura)")
        pin = st.text_input("PIN de administrador", type="password")
        if st.button("Entrar como administrador"):
            if pin == st.secrets.get("admin_pin", "sigali2027"):
                st.session_state.perfil = "admin"
                st.rerun()
            else:
                st.error("PIN incorreto.")

etapas = etapas_todas[etapas_todas["ciclo"] == ciclo_selecionado].copy() if ciclo_selecionado else etapas_todas.copy()
marcos = marcos_todos[marcos_todos["ciclo"] == ciclo_selecionado].copy() if ciclo_selecionado else marcos_todos.copy()

st.markdown(
    f"""<div style="background:#1E2A38;color:#F4F1E8;padding:1.1rem 1.6rem;
    border-radius:12px;border-bottom:4px double #A6772E;margin-bottom:1.4rem;">
    <div style="font-size:1.5rem;font-weight:700;letter-spacing:.02em;">🏛️ SIGALI</div>
    <div style="font-size:.82rem;opacity:.9;margin-top:.15rem;">Sistema Inteligente de Gestão da Agenda Legislativa da Indústria</div>
    <div style="font-size:.75rem;opacity:.65;margin-top:.4rem;">
    Confederação Nacional da Indústria &nbsp;·&nbsp; Ciclo: <strong>{ciclo_selecionado or '—'}</strong>
    &nbsp;·&nbsp; {pagina}</div>
    </div>""",
    unsafe_allow_html=True,
)


# ---------- Painel ----------

if pagina == "📊 Painel":
    etapas["_status_efetivo"] = etapas.apply(status_efetivo, axis=1)
    etapas["_critica"] = etapas.apply(eh_critica, axis=1)

    criticas = etapas[etapas["_critica"]].sort_values("data_prazo")
    if len(criticas):
        st.error(f"⚠️ {len(criticas)} demanda(s) crítica(s) exigem atenção")
        for _, r in criticas.head(15).iterrows():
            d = (r["data_prazo"] - date.today()).days if r["data_prazo"] else None
            rotulo = f"atrasada há {abs(d)} dia(s)" if r["_status_efetivo"] == "Atrasada" else ("vence hoje" if d == 0 else f"vence em {d} dia(s)")
            st.markdown(f"- **{r['nome']}** — {r['responsavel']}  ·  :red[{rotulo}]")

    col1, col2, col3, col4, col5 = st.columns(5)
    total = len(etapas) or 1
    concluidas = (etapas["_status_efetivo"] == "Resolvida").sum()
    col1.metric("Resolvidas", f"{round(100*concluidas/total)}%")
    col2.metric("Em andamento", int((etapas["_status_efetivo"] == "Em andamento").sum()))
    col3.metric("Em atraso", int((etapas["_status_efetivo"] == "Atrasada").sum()))
    col4.metric("Críticas", int(etapas["_critica"].sum()))
    col5.metric("Total de atividades", len(etapas))

    st.subheader("Acompanhamento por macroetapa", anchor=False)
    for m in MACROETAPAS:
        itens = etapas[etapas["macroetapa"] == m]
        if len(itens) == 0:
            continue
        conc = (itens["_status_efetivo"] == "Resolvida").sum()
        st.progress(conc / len(itens), text=f"{m} — {conc}/{len(itens)}")

    st.subheader("Visão individual por responsável", anchor=False)
    nomes = sorted(responsaveis["nome"].tolist())
    pessoa = st.selectbox("Selecione uma pessoa", [""] + nomes, placeholder="Selecione uma pessoa")
    if pessoa:
        itens_pessoa = etapas[etapas["responsavel"].str.contains(pessoa, case=False, na=False)]
        if len(itens_pessoa):
            tabela = itens_pessoa[["nome", "responsavel", "data_prazo", "_status_efetivo"]].reset_index(drop=True)
            tabela["data_prazo"] = tabela["data_prazo"].apply(lambda d: d.strftime("%d-%m-%Y") if pd.notna(d) else "")
            st.table(tabela)
        else:
            st.caption("Nenhuma atividade encontrada para esse nome.")


# ---------- Cronograma ----------

if pagina == "🗓️ Cronograma":
    with st.expander("Filtros", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        f_resp = c1.selectbox("Responsável", [""] + sorted(etapas["responsavel"].unique().tolist()), placeholder="Todos os responsáveis")
        f_macro = c2.selectbox("Macroetapa", [""] + MACROETAPAS, placeholder="Todas as macroetapas")
        f_situacao = c3.selectbox("Situação", [""] + STATUS_OPCOES + ["Atrasada", "Crítica"], placeholder="Todas as situações")
        f_tipo = c4.selectbox("Tipo de demanda", [""] + TIPOS_DEMANDA, placeholder="Todo tipo de demanda")
        c5, c6 = st.columns(2)
        f_de = c5.date_input("Prazo — de", value=None, format="DD-MM-YYYY")
        f_ate = c6.date_input("Prazo — até", value=None, format="DD-MM-YYYY")
        busca = st.text_input("Buscar por título ou descrição")

    df = etapas.copy()
    df["_status_efetivo"] = df.apply(status_efetivo, axis=1)
    df["_critica"] = df.apply(eh_critica, axis=1)
    if f_resp: df = df[df["responsavel"] == f_resp]
    if f_macro: df = df[df["macroetapa"] == f_macro]
    if f_tipo: df = df[df["tipo_demanda"] == f_tipo]
    if f_situacao == "Crítica": df = df[df["_critica"]]
    elif f_situacao: df = df[df["_status_efetivo"] == f_situacao]
    if f_de: df = df[df["data_prazo"] >= f_de]
    if f_ate: df = df[df["data_prazo"] <= f_ate]
    if busca: df = df[df["nome"].str.contains(busca, case=False, na=False) | df["descricao"].str.contains(busca, case=False, na=False)]
    df = df.sort_values("data_prazo")

    st.caption(f"{len(df)} de {len(etapas)} atividades exibidas")

    colunas = ["id", "nome", "descricao", "macroetapa", "tipo_demanda", "responsavel", "data_inicio", "data_prazo", "status", "sinalizado_diretor", "observacoes"]
    df_editar = df[colunas].reset_index(drop=True).copy()

    if is_admin:
        editado = st.data_editor(
            df_editar, num_rows="dynamic", use_container_width=True, hide_index=True,
            column_order=["nome", "responsavel", "macroetapa", "tipo_demanda", "data_inicio", "data_prazo", "status", "sinalizado_diretor", "descricao", "observacoes"],
            column_config={
                "nome": st.column_config.TextColumn("Atividade", width="large"),
                "descricao": st.column_config.TextColumn("Descrição", width="large"),
                "macroetapa": st.column_config.SelectboxColumn("Macroetapa", options=MACROETAPAS),
                "tipo_demanda": st.column_config.SelectboxColumn("Tipo de demanda", options=TIPOS_DEMANDA),
                "responsavel": st.column_config.TextColumn("Responsável"),
                "status": st.column_config.SelectboxColumn("Situação", options=STATUS_OPCOES),
                "observacoes": st.column_config.TextColumn("Observações", width="large"),
                "sinalizado_diretor": st.column_config.CheckboxColumn("Sinalizar p/ Diretor"),
                "id": st.column_config.TextColumn(disabled=True),
                "data_inicio": st.column_config.DateColumn("Início", format="DD-MM-YYYY"),
                "data_prazo": st.column_config.DateColumn("Prazo", format="DD-MM-YYYY"),
            },
            key="editor_cronograma",
        )
        if st.button("💾 Salvar alterações no Cronograma"):
            sincronizar("etapas", editado, df[colunas], chave="id", ciclo_forcado=ciclo_selecionado)
            st.success("Cronograma atualizado.")
            st.cache_resource.clear()
            st.rerun()
    else:
        st.dataframe(
            df_editar, use_container_width=True, hide_index=True,
            column_order=["nome", "responsavel", "macroetapa", "tipo_demanda", "data_inicio", "data_prazo", "status", "descricao", "observacoes"],
            column_config={
                "nome": st.column_config.TextColumn("Atividade", width="large"),
                "descricao": st.column_config.TextColumn("Descrição", width="large"),
                "macroetapa": "Macroetapa",
                "tipo_demanda": "Tipo de demanda",
                "responsavel": "Responsável",
                "status": "Situação",
                "observacoes": st.column_config.TextColumn("Observações", width="large"),
                "data_inicio": st.column_config.DateColumn("Início", format="DD-MM-YYYY"),
                "data_prazo": st.column_config.DateColumn("Prazo", format="DD-MM-YYYY"),
            },
        )

    if is_admin:
        with st.expander("📥 Importar nova agenda (novo ciclo, ex.: ALI 2028)"):
            st.caption(
                "Use isto quando chegar o cronograma de um novo ano. O ciclo atual (ex.: ALI 2027) "
                "continua guardado e acessível pelo seletor na barra lateral — nada se perde."
            )
            novo_ciclo = st.text_input("Nome do novo ciclo", placeholder="Ex.: ALI 2028")
            arquivo = st.file_uploader("Planilha do cronograma (mesmo modelo da Matriz RACI)", type=["xlsx"], key="upload_novo_ciclo")
            if arquivo and novo_ciclo:
                try:
                    xls_novo = pd.ExcelFile(arquivo)
                except Exception as ex:
                    st.error(f"Não consegui abrir esse arquivo: {ex}")
                    xls_novo = None
                if xls_novo:
                    aba_escolhida = st.selectbox("Qual aba tem o cronograma?", xls_novo.sheet_names, key="aba_novo_ciclo")
                    if aba_escolhida:
                        bruto = pd.read_excel(xls_novo, sheet_name=aba_escolhida, header=0)
                        bruto.columns = [str(c).strip() for c in bruto.columns]
                        obrigatorias = ["ID", "Título da Atividade", "Início"]
                        faltando = [c for c in obrigatorias if c not in bruto.columns]
                        if faltando:
                            st.error(f"Não encontrei as colunas {faltando} nessa aba. Confira se é a aba certa, ou me chama no chat que eu ajusto.")
                        else:
                            novas = parse_planilha_cronograma(bruto, novo_ciclo)
                            st.write(f"Encontrei **{len(novas)}** atividades para o ciclo **{novo_ciclo}**. Confira antes de confirmar:")
                            preview_df = pd.DataFrame(novas)[["id", "nome", "macroetapa", "responsavel", "data_prazo"]].reset_index(drop=True)
                            preview_df["data_prazo"] = pd.to_datetime(preview_df["data_prazo"], errors="coerce").dt.date
                            st.dataframe(
                                preview_df, use_container_width=True, hide_index=True,
                                column_order=["nome", "macroetapa", "responsavel", "data_prazo"],
                                column_config={
                                    "nome": st.column_config.TextColumn("Atividade", width="large"),
                                    "macroetapa": "Macroetapa",
                                    "responsavel": "Responsável",
                                    "data_prazo": st.column_config.DateColumn("Prazo", format="DD-MM-YYYY"),
                                },
                            )
                            if novo_ciclo in ciclos_disponiveis:
                                st.info(f"Já existe um ciclo chamado '{novo_ciclo}'. Confirmar vai atualizar/adicionar atividades dentro dele.")
                            if st.button("✅ Confirmar importação"):
                                for reg in novas:
                                    sb.table("etapas").upsert(reg).execute()
                                st.success(f"{len(novas)} atividades importadas para o ciclo '{novo_ciclo}'! Selecione o novo ciclo na barra lateral.")
                                st.cache_resource.clear()
                                st.rerun()


# ---------- Muniz ----------

if pagina == "🚩 Muniz":
    if ciclo_selecionado == "ALI 2027":
        st.warning(
            "Os marcos macro abaixo vieram rotulados como do ciclo **ALI 2026** na planilha original "
            "(datas de 2023 a 2026) — parecem um resquício do template do ano anterior. "
            "Revise e atualize as datas para o ciclo 2027 antes de apresentar ao Diretor."
        )

    st.subheader("Marcos macro do processo", anchor=False)
    marcos_diretor = marcos[marcos["manter_diretor"] == True].sort_values("data_sugerida").reset_index(drop=True)
    cols_marco = ["id", "status", "descricao", "data_sugerida", "observacoes", "manter_diretor"]
    if is_admin:
        marcos_editado = st.data_editor(
            marcos[cols_marco].reset_index(drop=True), num_rows="dynamic", use_container_width=True, hide_index=True,
            column_order=["descricao", "data_sugerida", "status", "manter_diretor", "observacoes"],
            column_config={
                "descricao": st.column_config.TextColumn("Descrição do marco", width="large"),
                "status": st.column_config.SelectboxColumn("Situação", options=STATUS_MARCO_OPCOES),
                "manter_diretor": st.column_config.CheckboxColumn("Manter na aba Muniz"),
                "observacoes": st.column_config.TextColumn("Observações", width="large"),
                "id": st.column_config.TextColumn(disabled=True),
                "data_sugerida": st.column_config.DateColumn("Data sugerida", format="DD-MM-YYYY"),
            },
            key="editor_marcos",
        )
        if st.button("💾 Salvar marcos"):
            sincronizar("marcos", marcos_editado, marcos[cols_marco], chave="id", ciclo_forcado=ciclo_selecionado)
            st.success("Marcos atualizados.")
            st.rerun()
    else:
        st.dataframe(
            marcos_diretor[["status", "descricao", "data_sugerida", "observacoes"]], use_container_width=True, hide_index=True,
            column_config={
                "status": "Situação",
                "descricao": st.column_config.TextColumn("Descrição do marco", width="large"),
                "observacoes": st.column_config.TextColumn("Observações", width="large"),
                "data_sugerida": st.column_config.DateColumn("Data sugerida", format="DD-MM-YYYY"),
            },
        )

    st.subheader("Atividades do cronograma sinalizadas para o Diretor", anchor=False)
    sinalizadas = etapas[etapas["sinalizado_diretor"] == True].sort_values("data_prazo").reset_index(drop=True)
    if len(sinalizadas):
        st.dataframe(
            sinalizadas[["nome", "macroetapa", "responsavel", "data_prazo", "status"]], use_container_width=True, hide_index=True,
            column_config={
                "nome": st.column_config.TextColumn("Atividade", width="large"),
                "macroetapa": "Macroetapa",
                "responsavel": "Responsável",
                "status": "Situação",
                "data_prazo": st.column_config.DateColumn("Prazo", format="DD-MM-YYYY"),
            },
        )
    else:
        st.caption('Nenhuma atividade sinalizada ainda. Marque "Sinalizar p/ Diretor" na aba Cronograma.')


# ---------- Responsáveis ----------

if pagina == "👥 Responsáveis":
    st.caption("Diretório de pessoas e áreas. Preencha e-mail/WhatsApp/Telegram para os alertas automáticos (fase 2).")

    etapas["_critica"] = etapas.apply(eh_critica, axis=1)
    categorias_disponiveis = sorted([c for c in responsaveis["categoria"].dropna().unique().tolist() if c])

    col_busca, col_cat = st.columns([2, 1])
    busca_resp = col_busca.text_input("🔎 Buscar por nome", placeholder="Digite um nome…")
    cat_filtro = col_cat.selectbox("Categoria", [""] + categorias_disponiveis, placeholder="Todas as categorias")

    lista = responsaveis.copy()
    if busca_resp:
        lista = lista[lista["nome"].str.contains(busca_resp, case=False, na=False)]
    if cat_filtro:
        lista = lista[lista["categoria"] == cat_filtro]
    lista = lista.sort_values("nome")

    st.caption(f"{len(lista)} de {len(responsaveis)} pessoas/áreas exibidas")

    if is_admin:
        with st.expander("➕ Adicionar novo responsável"):
            novo_nome = st.text_input("Nome / Área", key="novo_resp_nome")
            novo_cat = st.text_input("Categoria", key="novo_resp_cat", placeholder="Ex.: Área interna, Informação/SULEG…")
            c1, c2 = st.columns(2)
            novo_email = c1.text_input("E-mail", key="novo_resp_email")
            novo_whats = c2.text_input("WhatsApp", key="novo_resp_whats")
            if st.button("Adicionar", key="btn_novo_resp"):
                if novo_nome.strip():
                    sb.table("responsaveis").upsert({
                        "id": f"r-{slugify(novo_nome)}",
                        "nome": novo_nome.strip(),
                        "categoria": novo_cat.strip() or None,
                        "email": novo_email.strip() or None,
                        "whatsapp": novo_whats.strip() or None,
                    }).execute()
                    st.success(f"{novo_nome} adicionado(a).")
                    st.rerun()
                else:
                    st.warning("Informe ao menos o nome.")

    if not len(lista):
        st.caption("Nenhuma pessoa/área encontrada com esses filtros.")

    for _, r in lista.iterrows():
        contem = etapas["responsavel"].str.contains(r["nome"], case=False, na=False)
        qtd = int(contem.sum())
        criticas_qtd = int((contem & etapas["_critica"]).sum())

        rotulo = r["nome"] + (f"  ·  {r['categoria']}" if r.get("categoria") else "")
        with st.expander(rotulo):
            if is_admin:
                c1, c2 = st.columns(2)
                email_val = c1.text_input("E-mail", value=r.get("email") or "", key=f"email_{r['id']}")
                whats_val = c2.text_input("WhatsApp", value=r.get("whatsapp") or "", key=f"whats_{r['id']}")
                c3, c4 = st.columns(2)
                tg_val = c3.text_input("Telegram (chat ID)", value=r.get("telegram_chat_id") or "", key=f"tg_{r['id']}")
                cb_val = c4.text_input("WhatsApp — chave CallMeBot", value=r.get("callmebot_apikey") or "", key=f"cb_{r['id']}")
                cat_val = st.text_input("Categoria", value=r.get("categoria") or "", key=f"cat_{r['id']}")

                col_salvar, col_excluir, col_espaco = st.columns([1, 1, 3])
                if col_salvar.button("💾 Salvar", key=f"salvar_{r['id']}"):
                    sb.table("responsaveis").upsert({
                        "id": r["id"], "nome": r["nome"], "categoria": cat_val.strip() or None,
                        "email": email_val.strip() or None, "whatsapp": whats_val.strip() or None,
                        "telegram_chat_id": tg_val.strip() or None, "callmebot_apikey": cb_val.strip() or None,
                    }).execute()
                    st.success("Atualizado.")
                    st.rerun()
                if col_excluir.button("🗑️ Excluir", key=f"excluir_{r['id']}"):
                    sb.table("responsaveis").delete().eq("id", r["id"]).execute()
                    st.success("Removido.")
                    st.rerun()
            else:
                st.write(f"📧 {r.get('email') or '—'}")
                st.write(f"📱 WhatsApp: {r.get('whatsapp') or '—'}")

            st.caption(f"{qtd} atividade(s) associada(s)" + (f" · {criticas_qtd} crítica(s)" if criticas_qtd else ""))

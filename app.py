import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Revisador", page_icon="📝", layout="wide")

# Lista de disciplinas
SUBJECTS = [
    "Biologia", "Química", "Física", "Matemática", 
    "Gramática", "Literatura", "História", "Geografia", 
    "Filosofia/Sociologia", "Inglês", "Redação"
]

# URL Limpa (Removido o final /edit... para evitar Erro 400)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1TQO6bP2RmhZR_wBO7f8B7BEBbjonmt9f7ShqTdCxrg8"

# --- ESTILO VISUAL ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #f1f5f9; }
    .stButton>button { width: 100%; border-radius: 12px; font-weight: 800; background-color: #2563eb; color: white; border: none; padding: 0.6rem; }
    .stButton>button:hover { background-color: #1d4ed8; }
    div[data-testid="stMetricValue"] { font-weight: 900; color: #60a5fa; }
    div[data-testid="stExpander"] { border: 1px solid #1e293b; border-radius: 16px; background-color: #1e293b50; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- DIAGNÓSTICO DE CONEXÃO ---
with st.sidebar:
    st.header("🔍 Diagnóstico")
    if "connections" in st.secrets and "gsheets" in st.secrets.connections:
        st.success("Configuração encontrada!")
        if "service_account" in st.secrets.connections.gsheets:
            st.success("Chave JSON detetada!")
    else:
        st.error("Erro nos Secrets!")

# --- CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_all_data():
    try:
        # Tenta carregar as abas estudos e ajustes
        df_studies = conn.read(spreadsheet=SHEET_URL, worksheet="estudos", ttl=0)
        df_studies = df_studies.dropna(how='all')
        
        df_adj = conn.read(spreadsheet=SHEET_URL, worksheet="ajustes", ttl=0)
        df_adj = df_adj.dropna(how='all')
        
        return df_studies, df_adj
    except Exception as e:
        # Se as abas não existirem, retorna colunas vazias
        return (pd.DataFrame(columns=['data', 'materia', 'assunto', 'total', 'acertos', 'timestamp', 'erros']), 
                pd.DataFrame(columns=['id', 'date']))

def save_to_sheets(df_studies, df_adj):
    try:
        # Limpeza Total para evitar HTTP 400 Bad Request
        # Transformamos tudo em string para que o Google não rejeite formatos
        df_studies_save = df_studies.astype(str).replace("nan", "").replace("<NA>", "")
        df_adj_save = df_adj.astype(str).replace("nan", "").replace("<NA>", "")

        # Gravação forçada especificando a URL e a Worksheet
        conn.update(spreadsheet=SHEET_URL, worksheet="estudos", data=df_studies_save)
        conn.update(spreadsheet=SHEET_URL, worksheet="ajustes", data=df_adj_save)
        
        st.cache_data.clear()
        st.success("✅ Sincronizado com sucesso!")
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {str(e)}")
        return False

# Carregamento Inicial
df_sessions, df_overrides = load_all_data()

# --- LÓGICA DE CICLOS ---
def calculate_projections(sessions_df, overrides_df):
    if sessions_df.empty: return pd.DataFrame()
    projections = []
    
    # Prepara dados
    temp_df = sessions_df.copy()
    temp_df['timestamp'] = pd.to_numeric(temp_df['timestamp'], errors='coerce')
    valid_sessions = temp_df.dropna(subset=['timestamp'])
    if valid_sessions.empty: return pd.DataFrame()

    groups = valid_sessions.sort_values('timestamp').groupby(['materia', 'assunto'])
    overrides_dict = pd.Series(overrides_df.date.values, index=overrides_df.id).to_dict() if not overrides_df.empty else {}

    for (materia, assunto), group in groups:
        latest = group.iloc[-1]
        initial = group.iloc[0]
        num = len(group)
        
        try:
            acc = (float(latest['acertos']) / float(latest['total'] if float(latest['total']) > 0 else 1)) * 100
            initial_acc = (float(initial['acertos']) / (float(initial['total']) if float(initial['total']) > 0 else 1)) * 100
        except: acc, initial_acc = 0, 0
            
        try: last_dt = datetime.strptime(str(latest['data']), '%Y-%m-%d').date()
        except: last_dt = datetime.now().date()
            
        days, action, case_type = 1, "", ""
        
        if num > 1 and acc < 70: days, action, case_type = 1, "🚨 Rebaixado: Foco na base.", "Caso A"
        elif initial_acc < 70:
            if num == 1: days, action, case_type = 1, "D+1: Refazer erros.", "Caso A"
            elif num == 2:
                if acc >= 100: days, action, case_type = 3, "D+4: Estabilidade.", "Caso A"
                else: days, action, case_type = 1, "⚠️ Repetir D+1.", "Caso A"
            else:
                if acc > 85: days, action, case_type = 15, "✅ Promovido.", "Caso C"
                else: days, action, case_type = 7, "❌ Reforço.", "Caso B"
        elif initial_acc <= 85:
            if num == 1: days, action, case_type = 7, "D+7: Bateria mista.", "Caso B"
            else:
                if acc > 90: days, action, case_type = 30, "🔥 Maestria.", "Caso C"
                else: days, action, case_type = 14, "Fixação.", "Caso B"
        else:
            if acc < 80: days, action, case_type = 7, "📉 Queda rendimento.", "Caso B"
            elif num == 1: days, action, case_type = 15, "D+15: Simulado.", "Caso C"
            else: days, action, case_type = 45, "Manutenção.", "Caso C"

        proj_dt = last_dt + timedelta(days=max(days, 1))
        proj_str = proj_dt.strftime('%Y-%m-%d')
        key = f"{materia}-{assunto}".lower().replace(" ", "").replace("/", "-")
        if key in overrides_dict: proj_str = overrides_dict[key]

        projections.append({'Data': proj_str, 'Materia': materia, 'Assunto': assunto, 'Ação': action, 'Caso': case_type, 'Nota': f"{acc:.0f}%", 'Erros': latest['erros'], 'Passo': num, 'Key': key})
    
    return pd.DataFrame(projections)

# --- INTERFACE ---
st.title("📝 REVISADOR")

tabs = st.tabs(["📅 Agenda", "➕ Registrar", "📊 Desempenho", "📜 Histórico"])

with tabs[0]: # AGENDA
    st.subheader("Cronograma")
    proj_df = calculate_projections(df_sessions, df_overrides)
    if not proj_df.empty:
        proj_df = proj_df.sort_values('Data')
        for _, row in proj_df.iterrows():
            with st.expander(f"{row['Data']} | {row['Materia']} - {row['Assunto']}"):
                st.markdown(f"**Fase:** {row['Caso']} | **Ação:** {row['Ação']}")
                if str(row['Erros']) != "" and str(row['Erros']) != "nan": st.error(f"⚠️ Erros: {row['Erros']}")
                new_d = st.date_input("Ajustar data", value=datetime.strptime(row['Data'], '%Y-%m-%d'), key=f"d_{row['Key']}")
                if new_d.strftime('%Y-%m-%d') != row['Data']:
                    new_o = pd.DataFrame([{'id': row['Key'], 'date': new_d.strftime('%Y-%m-%d')}])
                    df_overrides = pd.concat([df_overrides[df_overrides.id != row['Key']], new_o], ignore_index=True)
                    save_to_sheets(df_sessions, df_overrides); st.rerun()
                if st.button("Iniciar Estudo", key=f"b_{row['Key']}"):
                    st.session_state.prefill = row; st.success("Dados copiados!")
    else: st.write("Nada pendente.")

with tabs[1]: # REGISTRAR
    st.subheader("Novo Registro")
    pre = st.session_state.get('prefill', None)
    with st.form("f_reg", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            m_in = st.selectbox("Matéria", SUBJECTS, index=SUBJECTS.index(pre['Materia']) if pre else 0)
            d_in = st.date_input("Data", value=datetime.now())
        with c2: a_in = st.text_input("Assunto", value=pre['Assunto'] if pre else "")
        c3, c4 = st.columns(2)
        with c3: t_in = st.number_input("Total Questões", min_value=1, value=20)
        with c4: ac_in = st.number_input("Acertos", min_value=0, value=0)
        err_in = st.text_area("IDs das Questões Erradas")
        if st.form_submit_button("Salvar Registro"):
            new_r = pd.DataFrame([{'data': d_in.strftime('%Y-%m-%d'), 'materia': m_in, 'assunto': a_in, 'total': int(t_in), 'acertos': int(ac_in), 'timestamp': datetime.now().timestamp(), 'erros': err_in}])
            df_sessions = pd.concat([df_sessions, new_r], ignore_index=True)
            key = f"{m_in}-{a_in}".lower().replace(" ", "").replace("/", "-")
            if save_to_sheets(df_sessions, df_overrides[df_overrides.id != key]):
                st.session_state.prefill = None; st.rerun()

with tabs[2]: # DESEMPENHO
    if not df_sessions.empty:
        df_calc = df_sessions.copy()
        df_calc['total'] = pd.to_numeric(df_calc['total'], errors='coerce').fillna(1)
        df_calc['acertos'] = pd.to_numeric(df_calc['acertos'], errors='coerce').fillna(0)
        df_calc['nota'] = (df_calc['acertos'] / df_calc['total']) * 100
        st.metric("Aproveitamento Geral", f"{df_calc['nota'].mean():.1f}%")
        st.bar_chart(df_calc.groupby('materia')['nota'].mean().reindex(SUBJECTS).fillna(0))
    else: st.info("Sem dados.")

with tabs[3]: # HISTÓRICO
    if not df_sessions.empty:
        st.dataframe(df_sessions.sort_values('timestamp', ascending=False), hide_index=True, use_container_width=True)
        if st.checkbox("Excluir linha"):
            idx = st.number_input("Índice", min_value=0, max_value=len(df_sessions)-1, step=1)
            if st.button("Confirmar Exclusão"):
                df_sessions = df_sessions.drop(df_sessions.index[idx])
                save_to_sheets(df_sessions, df_overrides); st.rerun()

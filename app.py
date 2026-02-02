import streamlit as st
import pandas as pd
import gspread
from datetime import datetime, timedelta
import json

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Revisador", page_icon="📝", layout="wide")

# Lista de disciplinas
SUBJECTS = [
    "Biologia", "Química", "Física", "Matemática", 
    "Gramática", "Literatura", "História", "Geografia", 
    "Filosofia/Sociologia", "Inglês", "Redação"
]

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

# --- CONEXÃO DIRETA COM GSPREAD ---
@st.cache_resource
def get_gspread_client():
    try:
        # Puxa o JSON direto do segredo service_account
        info = json.loads(st.secrets["connections"]["gsheets"]["service_account"])
        client = gspread.service_account_from_dict(info)
        return client
    except Exception as e:
        st.error(f"Erro na chave JSON: {e}")
        return None

def get_sheet():
    client = get_gspread_client()
    if client:
        # Abre pelo ID que é mais seguro
        return client.open_by_key("1TQO6bP2RmhZR_wBO7f8B7BEBbjonmt9f7ShqTdCxrg8")
    return None

def load_data():
    sheet = get_sheet()
    if not sheet: return pd.DataFrame(), pd.DataFrame()
    try:
        df_studies = pd.DataFrame(sheet.worksheet("estudos").get_all_records())
        df_adj = pd.DataFrame(sheet.worksheet("ajustes").get_all_records())
        return df_studies, df_adj
    except Exception:
        return pd.DataFrame(columns=['data', 'materia', 'assunto', 'total', 'acertos', 'timestamp', 'erros']), \
               pd.DataFrame(columns=['id', 'date'])

# --- FUNÇÕES DE SALVAMENTO ---
def save_session(new_row):
    sheet = get_sheet()
    if sheet:
        ws = sheet.worksheet("estudos")
        # Transforma o dicionário em uma lista na ordem certa
        row_list = [new_row['data'], new_row['materia'], new_row['assunto'], 
                    new_row['total'], new_row['acertos'], new_row['timestamp'], new_row['erros']]
        ws.append_row(row_list)
        return True
    return False

def save_override(key, date_str):
    sheet = get_sheet()
    if sheet:
        ws = sheet.worksheet("ajustes")
        # Verifica se já existe e atualiza ou adiciona
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty and key in df['id'].values:
            # Encontra a linha (gspread começa em 1, cabeçalho é 1, então +2)
            idx = df[df['id'] == key].index[0] + 2
            ws.update_cell(idx, 2, date_str)
        else:
            ws.append_row([key, date_str])
        return True
    return False

# Inicializar dados
df_sessions, df_overrides = load_data()

# --- LÓGICA DE CICLOS (V3.2) ---
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
        
        if num > 1 and acc < 70: days, action, case_type = 1, "🚨 Rebaixado: Reiniciar Caso A.", "Caso A"
        elif initial_acc < 70:
            if num == 1: days, action, case_type = 1, "D+1: Refazer erros.", "Caso A"
            elif num == 2:
                if acc >= 100: days, action, case_type = 3, "D+4: Estabilidade.", "Caso A"
                else: days, action, case_type = 1, "⚠️ Repetir D+1.", "Caso A"
            else:
                if acc > 85: days, action, case_type = 15, "✅ Promovido.", "Caso C"
                else: days, action, case_type = 7, "❌ Reforço.", "Caso B"
        elif initial_acc <= 85:
            if num == 1: days, action, case_type = 7, "D+7: Lapidação.", "Caso B"
            else:
                if acc > 90: days, action, case_type = 30, "🔥 Maestria.", "Caso C"
                else: days, action, case_type = 14, "Fixação.", "Caso B"
        else:
            if acc < 80: days, action, case_type = 7, "📉 Queda.", "Caso B"
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
    st.subheader("Cronograma Inteligente")
    proj_df = calculate_projections(df_sessions, df_overrides)
    if not proj_df.empty:
        proj_df = proj_df.sort_values('Data')
        for _, row in proj_df.iterrows():
            with st.expander(f"{row['Data']} | {row['Materia']} - {row['Assunto']}"):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(f"**Fase:** {row['Caso']} | **Ação:** {row['Ação']}")
                    if str(row['Erros']) != "" and str(row['Erros']) != "nan": st.error(f"⚠️ Erros: {row['Erros']}")
                with c2:
                    new_d = st.date_input("Mudar data", value=datetime.strptime(row['Data'], '%Y-%m-%d'), key=f"d_{row['Key']}")
                    if new_d.strftime('%Y-%m-%d') != row['Data']:
                        if save_override(row['Key'], new_d.strftime('%Y-%m-%d')):
                            st.success("Data alterada!"); st.rerun()
                    if st.button("Iniciar Estudo", key=f"b_{row['Key']}"):
                        st.session_state.prefill = row; st.success("Copiado!")
    else: st.write("Nada pendente.")

with tabs[1]: # REGISTRAR
    st.subheader("Novo Registro")
    pre = st.session_state.get('prefill', None)
    with st.form("f_reg", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            m_in = st.selectbox("Matéria", SUBJECTS, index=SUBJECTS.index(pre['Materia']) if pre else 0)
            d_in = st.date_input("Data Realizada", value=datetime.now())
        with c2: a_in = st.text_input("Assunto", value=pre['Assunto'] if pre else "")
        c3, c4 = st.columns(2)
        with c3: t_in = st.number_input("Total Questões", min_value=1, value=20)
        with c4: ac_in = st.number_input("Acertos", min_value=0, value=0)
        err_in = st.text_area("Questões Erradas (IDs)")
        if st.form_submit_button("Salvar Registro"):
            new_r = {
                'data': d_in.strftime('%Y-%m-%d'), 'materia': m_in, 'assunto': a_in, 
                'total': int(t_in), 'acertos': int(ac_in), 
                'timestamp': datetime.now().timestamp(), 'erros': err_in
            }
            if save_session(new_r):
                st.session_state.prefill = None; st.success("Sessão salva!"); st.rerun()

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

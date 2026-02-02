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
    div[data-testid="stMetricValue"] { font-weight: 900; color: #60a5fa; }
    div[data-testid="stExpander"] { border: 1px solid #1e293b; border-radius: 16px; background-color: #1e293b50; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- CONEXÃO INDIVIDUAL (MÉTODO DIRETO) ---
@st.cache_resource
def get_gspread_client():
    try:
        # Puxa o conteúdo do segredo service_account
        # Importante: O Streamlit pode carregar isto como um dicionário ou string
        raw_info = st.secrets["connections"]["gsheets"]["service_account"]
        
        if isinstance(raw_info, str):
            info = json.loads(raw_info)
        else:
            # Se já for um dicionário (carregado via TOML), criamos uma cópia para editar
            info = dict(raw_info)
        
        # CORREÇÃO ÚNICA E NECESSÁRIA:
        # Transforma o texto "\n" em quebras de linha reais para o motor de criptografia
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")

        return gspread.service_account_from_dict(info)
    except Exception as e:
        st.error(f"Erro Crítico de Autenticação: {e}")
        return None

def get_sheet():
    client = get_gspread_client()
    if client:
        try:
            # Abre a tua planilha pelo ID fixo para evitar erros de URL
            return client.open_by_key("1TQO6bP2RmhZR_wBO7f8B7BEBbjonmt9f7ShqTdCxrg8")
        except Exception as e:
            st.error(f"Erro ao abrir a planilha: {e}. Verifique se o e-mail do robô é EDITOR na planilha.")
    return None

def load_data():
    sheet = get_sheet()
    if not sheet: return pd.DataFrame(), pd.DataFrame()
    try:
        # Lê os dados existentes
        df_studies = pd.DataFrame(sheet.worksheet("estudos").get_all_records())
        df_adj = pd.DataFrame(sheet.worksheet("ajustes").get_all_records())
        return df_studies, df_adj
    except Exception:
        # Retorna tabelas vazias se a planilha estiver limpa
        return pd.DataFrame(columns=['data', 'materia', 'assunto', 'total', 'acertos', 'timestamp', 'erros']), \
               pd.DataFrame(columns=['id', 'date'])

# --- FUNÇÕES DE ESCRITA ---
def save_session(new_row):
    sheet = get_sheet()
    if sheet:
        try:
            ws = sheet.worksheet("estudos")
            # Garante a ordem: data, materia, assunto, total, acertos, timestamp, erros
            ws.append_row([
                new_row['data'], new_row['materia'], new_row['assunto'],
                new_row['total'], new_row['acertos'], new_row['timestamp'], new_row['erros']
            ])
            return True
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")
    return False

def save_override(key, date_str):
    sheet = get_sheet()
    if sheet:
        try:
            ws = sheet.worksheet("ajustes")
            data = ws.get_all_records()
            df = pd.DataFrame(data)
            if not df.empty and key in df['id'].values:
                # Atualiza linha existente (+2 porque gspread começa em 1 e tem cabeçalho)
                idx = df[df['id'] == key].index[0] + 2
                ws.update_cell(idx, 2, date_str)
            else:
                ws.append_row([key, date_str])
            return True
        except Exception as e:
            st.error(f"Erro ao mudar data: {e}")
    return False

# Inicializar os dados
df_sessions, df_overrides = load_data()

# --- MOTOR DE CÁLCULO (A-B-C) ---
def calculate_projections(sessions_df, overrides_df):
    if sessions_df.empty: return pd.DataFrame()
    
    df = sessions_df.copy()
    # Converte colunas para números para evitar erros de cálculo
    df['total'] = pd.to_numeric(df['total'], errors='coerce').fillna(1)
    df['acertos'] = pd.to_numeric(df['acertos'], errors='coerce').fillna(0)
    df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
    
    valid_df = df.dropna(subset=['timestamp'])
    if valid_df.empty: return pd.DataFrame()

    groups = valid_df.sort_values('timestamp').groupby(['materia', 'assunto'])
    over_dict = pd.Series(overrides_df.date.values, index=overrides_df.id).to_dict() if not overrides_df.empty else {}

    projections = []
    for (materia, assunto), group in groups:
        latest = group.iloc[-1]
        initial = group.iloc[0]
        num = len(group)
        
        acc = (float(latest['acertos']) / float(latest['total'] if latest['total'] > 0 else 1)) * 100
        init_acc = (float(initial['acertos']) / float(initial['total'] if initial['total'] > 0 else 1)) * 100
            
        try: last_dt = datetime.strptime(str(latest['data']), '%Y-%m-%d').date()
        except: last_dt = datetime.now().date()
            
        days = 1
        action, case_type = "", ""
        
        # Lógica de Revisão
        if num > 1 and acc < 70: days, action, case_type = 1, "🚨 Rebaixado: Refazer base.", "Caso A"
        elif init_acc < 70:
            if num == 1: days, action, case_type = 1, "D+1: Refazer erros.", "Caso A"
            elif num == 2: days, action, case_type = (3 if acc >= 100 else 1), "Teste de Estabilidade.", "Caso A"
            else: days, action, case_type = (15 if acc > 85 else 7), "Promoção Ciclo.", "Caso C/B"
        elif init_acc <= 85:
            days, action, case_type = (30, "Maestria.", "Caso C") if acc > 90 else (14, "Fixação.", "Caso B")
        else:
            days, action, case_type = (45, "Manutenção.", "Caso C") if acc >= 80 else (7, "Queda nota.", "Caso B")

        p_str = (last_dt + timedelta(days=max(days, 1))).strftime('%Y-%m-%d')
        key = f"{materia}-{assunto}".lower().replace(" ", "").replace("/", "-")
        if key in over_dict: p_str = over_dict[key]

        projections.append({'Data': p_str, 'Materia': materia, 'Assunto': assunto, 'Ação': action, 'Caso': case_type, 'Nota': f"{acc:.0f}%", 'Erros': latest['erros'], 'Key': key})
    
    return pd.DataFrame(projections)

# --- INTERFACE ---
st.title("📝 REVISADOR")

with st.sidebar:
    if st.button("🔄 Sincronizar Agora"):
        st.cache_resource.clear()
        st.rerun()
    st.write("---")
    st.caption("Acesso Individual Arthur")

tab1, tab2, tab3, tab4 = st.tabs(["📅 Agenda", "➕ Registrar", "📊 Desempenho", "📜 Histórico"])

with tab1:
    st.subheader("Cronograma")
    proj_df = calculate_projections(df_sessions, df_overrides)
    if not proj_df.empty:
        for _, row in proj_df.sort_values('Data').iterrows():
            with st.expander(f"{row['Data']} | {row['Materia']} - {row['Assunto']}"):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.write(f"**Fase:** {row['Caso']}")
                    st.info(row['Ação'])
                    if str(row['Erros']) and str(row['Erros']) != 'nan' and row['Erros'] != "":
                        st.error(f"Erros: {row['Erros']}")
                with c2:
                    new_d = st.date_input("Mudar data", value=datetime.strptime(row['Data'], '%Y-%m-%d'), key=f"d_{row['Key']}")
                    if new_d.strftime('%Y-%m-%d') != row['Data']:
                        if save_override(row['Key'], new_d.strftime('%Y-%m-%d')): st.rerun()
                    if st.button("Iniciar Estudo", key=f"b_{row['Key']}"):
                        st.session_state.prefill = row
    else: st.write("Agenda vazia. Registre um estudo!")

with tab2:
    pre = st.session_state.get('prefill', None)
    with st.form("form_reg", clear_on_submit=True):
        m_in = st.selectbox("Matéria", SUBJECTS, index=SUBJECTS.index(pre['Materia']) if pre else 0)
        a_in = st.text_input("Assunto", value=pre['Assunto'] if pre else "")
        col1, col2 = st.columns(2)
        t_in = col1.number_input("Total Questões", min_value=1, value=20)
        ac_in = col2.number_input("Acertos", min_value=0, value=0)
        e_in = st.text_area("Questões Erradas")
        if st.form_submit_button("Salvar Registro"):
            new_r = {'data': datetime.now().strftime('%Y-%m-%d'), 'materia': m_in, 'assunto': a_in, 'total': int(t_in), 'acertos': int(ac_in), 'timestamp': datetime.now().timestamp(), 'erros': str(e_in)}
            if save_session(new_r):
                st.session_state.prefill = None
                st.rerun()

with tab3:
    if not df_sessions.empty:
        df_c = df_sessions.copy()
        df_c['nota'] = (pd.to_numeric(df_c['acertos']) / pd.to_numeric(df_c['total'])) * 100
        st.metric("Média Geral", f"{df_c['nota'].mean():.1f}%")
        st.bar_chart(df_c.groupby('materia')['nota'].mean().reindex(SUBJECTS).fillna(0))

with tab4:
    if not df_sessions.empty:
        st.dataframe(df_sessions.sort_values('timestamp', ascending=False), hide_index=True, use_container_width=True)

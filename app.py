import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Revisador", page_icon="📚", layout="wide")

# Lista de disciplinas original
SUBJECTS = [
    "Biologia", "Química", "Física", "Matemática", 
    "Gramática", "Literatura", "História", "Geografia", 
    "Filosofia/Sociologia", "Inglês", "Redação"
]

ERROR_TYPES = ["Falta de Conteúdo", "Interpretação", "Atenção/Distração", "Tempo Insuficiente", "Cálculo/Sinal", "Pegadinha"]

# --- ESTILO VISUAL (CSS) ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #f1f5f9; }
    .stButton>button { 
        width: 100%; 
        border-radius: 12px; 
        font-weight: 800; 
        background-color: #2563eb; 
        color: white; 
        border: none; 
        padding: 0.6rem;
        transition: all 0.3s;
    }
    .stButton>button:hover { background-color: #1d4ed8; transform: translateY(-2px); }
    div[data-testid="stMetricValue"] { font-weight: 900; color: #60a5fa; }
    div[data-testid="stExpander"] { 
        border: 1px solid #1e293b; 
        border-radius: 16px; 
        background-color: #1e293b50; 
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONEXÃO E DADOS ---
# A conexão usa as Secrets configuradas no Streamlit Cloud
conn = st.connection("gsheets", type=GSheetsConnection)

def load_all_data():
    try:
        # Carrega dados das abas com tratamento de erro
        df_studies = conn.read(worksheet="estudos", ttl=0)
        df_studies = df_studies.dropna(how='all')
        
        df_adj = conn.read(worksheet="ajustes", ttl=0)
        df_adj = df_adj.dropna(how='all')
        
        return df_studies, df_adj
    except Exception as e:
        # Se as abas não existirem ou houver erro de permissão
        st.warning("Aguardando conexão inicial com a planilha ou abas não encontradas.")
        return (pd.DataFrame(columns=['data', 'materia', 'assunto', 'total', 'acertos', 'timestamp', 'erros']), 
                pd.DataFrame(columns=['id', 'date']))

def save_to_sheets(df_studies, df_adj):
    try:
        # 1. Normalização de dados (Evita UnsupportedOperationError por tipos errados)
        df_studies = df_studies.fillna("")
        df_studies['total'] = pd.to_numeric(df_studies['total'], errors='coerce').fillna(0).astype(int)
        df_studies['acertos'] = pd.to_numeric(df_studies['acertos'], errors='coerce').fillna(0).astype(int)
        df_studies['timestamp'] = pd.to_numeric(df_studies['timestamp'], errors='coerce').fillna(0)
        
        df_adj = df_adj.fillna("")

        # 2. Gravação forçada nas abas
        conn.update(worksheet="estudos", data=df_studies)
        conn.update(worksheet="ajustes", data=df_adj)
        
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Falha Crítica na Planilha: {str(e)}")
        st.info("💡 Dica: Verifique se ativou a 'Google Drive API' além da 'Google Sheets API' no console.")
        return False

# Carregamento inicial
df_sessions, df_overrides = load_all_data()

# --- ENGINE DE PROJEÇÃO (LÓGICA V3.2) ---
def calculate_projections(sessions_df, overrides_df):
    projections = []
    if sessions_df.empty:
        return pd.DataFrame()
    
    # Processa apenas linhas válidas
    sessions_df['timestamp'] = pd.to_numeric(sessions_df['timestamp'], errors='coerce')
    valid_sessions = sessions_df.dropna(subset=['timestamp'])
    
    if valid_sessions.empty: return pd.DataFrame()

    # Agrupa por Assunto para definir o estado do ciclo
    groups = valid_sessions.sort_values('timestamp').groupby(['materia', 'assunto'])
    overrides_dict = pd.Series(overrides_df.date.values, index=overrides_df.id).to_dict() if not overrides_df.empty else {}

    for (materia, assunto), group in groups:
        latest = group.iloc[-1]
        initial = group.iloc[0]
        num = len(group)
        
        try:
            acc = (float(latest['acertos']) / float(latest['total'] if float(latest['total']) > 0 else 1)) * 100
            initial_acc = (float(initial['acertos']) / float(initial['total'] if float(initial['total']) > 0 else 1)) * 100
        except:
            acc = 0
            initial_acc = 0
            
        try:
            last_dt = datetime.strptime(str(latest['data']), '%Y-%m-%d').date()
        except:
            last_dt = datetime.now().date()
            
        days = 1
        action, case_type, urgency = "", "", "low"
        
        # Lógica ABC robusta
        if num > 1 and acc < 70:
            days, action, case_type, urgency = 1, "🚨 Rebaixado: Foco total na base do Caso A.", "Caso A - Rebaixado", "high"
        elif initial_acc < 70:
            if num == 1: days, action, case_type, urgency = 1, "D+1: Refazer erros específicos.", "Caso A - Resgate", "high"
            elif num == 2:
                if acc >= 100: days, action, case_type, urgency = 3, "D+4: Teste de estabilidade.", "Caso A - Estabilidade", "medium"
                else: days, action, case_type, urgency = 1, "⚠️ Repetir D+1: Necessário 100% de acerto.", "Caso A - Repetir", "high"
            else:
                if acc > 85: days, action, case_type, urgency = 15, "✅ Promovido: Manutenção.", "Caso A -> C", "low"
                else: days, action, case_type, urgency = 7, "❌ Reforço: Revisão em 7 dias.", "Caso A -> B", "medium"
        elif initial_acc <= 85:
            if num == 1: days, action, case_type, urgency = 7, "D+7: Bateria mista (Obj+Disc).", "Caso B - Lapidação", "medium"
            else:
                if acc > 90: days, action, case_type, urgency = 30, "🔥 Maestria: Próxima em 30 dias.", "Caso B -> C", "low"
                else: days, action, case_type, urgency = 14, "Fixação: Bateria em 14 dias.", "Caso B - Fixação", "medium"
        else:
            if acc < 80: days, action, case_type, urgency = 7, "📉 Queda (<80%): Retorno ciclo 7 dias.", "Caso C -> B", "medium"
            elif num == 1: days, action, case_type, urgency = 15, "D+15: Simulado focado em velocidade.", "Caso C - Maestria", "low"
            else: days, action, case_type, urgency = 45, "D+45: Manutenção Permanente.", "Caso C - Manutenção", "low"

        proj_dt = last_dt + timedelta(days=max(days, 1))
        proj_str = proj_dt.strftime('%Y-%m-%d')
        
        key = f"{materia}-{assunto}".lower().replace(" ", "").replace("/", "-")
        if key in overrides_dict:
            proj_str = overrides_dict[key]

        projections.append({
            'Data': proj_str, 'Materia': materia, 'Assunto': assunto,
            'Ação': action, 'Caso': case_type, 'Nota': f"{acc:.0f}%",
            'Erros': latest['erros'], 'Passo': num, 'Key': key, 'Urgency': urgency
        })
    
    return pd.DataFrame(projections)

# --- INTERFACE ---
st.title("📝 REVISADOR")

tabs = st.tabs(["📅 Agenda", "➕ Registrar", "📊 Desempenho", "📜 Histórico"])

with tabs[0]: # AGENDA
    st.subheader("Cronograma Inteligente")
    proj_df = calculate_projections(df_sessions, df_overrides)
    
    if not proj_df.empty:
        proj_df = proj_df.sort_values('Data')
        filtro_agenda = st.selectbox("Filtrar Matéria", ["Todas"] + SUBJECTS, key="f_agenda")
        if filtro_agenda != "Todas":
            proj_df = proj_df[proj_df.Materia == filtro_agenda]

        for _, row in proj_df.iterrows():
            with st.expander(f"{row['Data']} | {row['Materia']} - {row['Assunto']}"):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(f"**Status:** {row['Caso']} | **Sessão:** #{row['Passo']}")
                    st.info(f"👉 {row['Ação']}")
                    if row['Erros'] and str(row['Erros']) != "nan":
                        st.error(f"⚠️ Refazer erros: {row['Erros']}")
                with c2:
                    new_dt = st.date_input("Mudar data", value=datetime.strptime(row['Data'], '%Y-%m-%d'), key=f"date_{row['Key']}")
                    if new_dt.strftime('%Y-%m-%d') != row['Data']:
                        new_ov = pd.DataFrame([{'id': row['Key'], 'date': new_dt.strftime('%Y-%m-%d')}])
                        df_overrides = df_overrides[df_overrides.id != row['Key']] if not df_overrides.empty else df_overrides
                        df_overrides = pd.concat([df_overrides, new_ov], ignore_index=True)
                        save_to_sheets(df_sessions, df_overrides)
                        st.rerun()
                    if st.button("Iniciar Estudo", key=f"btn_{row['Key']}"):
                        st.session_state.prefill = row
                        st.success("Copiado! Vá para 'Registrar'.")
    else:
        st.write("Sem revisões agendadas.")

with tabs[1]: # REGISTRAR
    st.subheader("Novo Registro de Estudo")
    pre = st.session_state.get('prefill', None)
    with st.form("form_reg", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            m_input = st.selectbox("Matéria", SUBJECTS, index=SUBJECTS.index(pre['Materia']) if pre else 0)
            d_input = st.date_input("Data do Estudo", value=datetime.now())
        with c2:
            a_input = st.text_input("Assunto", value=pre['Assunto'] if pre else "")
        c3, c4 = st.columns(2)
        with c3:
            t_input = st.number_input("Total de Questões", min_value=1, value=20)
        with c4:
            ac_input = st.number_input("Acertos", min_value=0, value=0)
        err_input = st.text_area("Quais questões errou? (Ex: Q02, Q05)")
        if st.form_submit_button("Salvar e Projetar"):
            new_row = pd.DataFrame([{
                'data': d_input.strftime('%Y-%m-%d'), 'materia': m_input, 'assunto': a_input,
                'total': int(t_input), 'acertos': int(ac_input), 'timestamp': datetime.now().timestamp(),
                'erros': err_input
            }])
            df_sessions = pd.concat([df_sessions, new_row], ignore_index=True)
            key = f"{m_input}-{a_input}".lower().replace(" ", "").replace("/", "-")
            df_overrides = df_overrides[df_overrides.id != key] if not df_overrides.empty else df_overrides
            if save_to_sheets(df_sessions, df_overrides):
                st.session_state.prefill = None
                st.success("Salvo com sucesso!")
                st.rerun()

with tabs[2]: # DESEMPENHO
    if not df_sessions.empty:
        df_sessions['total'] = pd.to_numeric(df_sessions['total'], errors='coerce').fillna(1)
        df_sessions['acertos'] = pd.to_numeric(df_sessions['acertos'], errors='coerce').fillna(0)
        df_sessions['nota'] = (df_sessions['acertos'] / df_sessions['total']) * 100
        m1, m2 = st.columns(2)
        m1.metric("Aproveitamento Geral", f"{df_sessions['nota'].mean():.1f}%")
        m2.metric("Total de Exercícios", int(df_sessions['total'].sum()))
        subj_data = df_sessions.groupby('materia')['nota'].mean().reindex(SUBJECTS).fillna(0).reset_index()
        st.bar_chart(subj_data.set_index('materia'))
    else:
        st.info("Registre estudos para ver o gráfico.")

with tabs[3]: # HISTÓRICO
    if not df_sessions.empty:
        st.dataframe(df_sessions.sort_values('timestamp', ascending=False), hide_index=True, use_container_width=True)
        if st.checkbox("Excluir registro"):
            idx_del = st.number_input("ID da linha para apagar", min_value=0, max_value=len(df_sessions)-1, step=1)
            if st.button("Confirmar Exclusão"):
                df_sessions = df_sessions.drop(df_sessions.index[idx_del])
                save_to_sheets(df_sessions, df_overrides)
                st.rerun()

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
# Simula o visual "Dark Premium" da versão original
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #f1f5f9; }
    
    /* Botões */
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
    
    /* Cards e Expanders */
    div[data-testid="stMetricValue"] { font-weight: 900; color: #60a5fa; }
    div[data-testid="stExpander"] { 
        border: 1px solid #1e293b; 
        border-radius: 16px; 
        background-color: #1e293b50; 
        margin-bottom: 10px;
    }
    
    /* Badges de Caso */
    .badge {
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 10px;
        font-weight: bold;
        text-transform: uppercase;
    }
    .badge-a { background-color: #f43f5e20; color: #f43f5e; border: 1px solid #f43f5e40; }
    .badge-b { background-color: #fbbf2420; color: #fbbf24; border: 1px solid #fbbf2440; }
    .badge-c { background-color: #10b98120; color: #10b981; border: 1px solid #10b98140; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES AUXILIARES ---
def get_local_date_str(date=None):
    if date is None: date = datetime.now()
    return date.strftime('%Y-%m-%d')

# --- CONEXÃO E DADOS ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_all_data():
    try:
        df_studies = conn.read(worksheet="estudos", ttl=0)
        df_studies = df_studies.dropna(how='all')
        df_adj = conn.read(worksheet="ajustes", ttl=0)
        df_adj = df_adj.dropna(how='all')
        return df_studies, df_adj
    except:
        return (pd.DataFrame(columns=['data', 'materia', 'assunto', 'total', 'acertos', 'timestamp', 'erros']), 
                pd.DataFrame(columns=['id', 'date']))

def save_to_sheets(df_studies, df_adj):
    conn.update(worksheet="estudos", data=df_studies)
    conn.update(worksheet="ajustes", data=df_adj)
    st.cache_data.clear()

df_sessions, df_overrides = load_all_data()

# --- ENGINE DE PROJEÇÃO (LÓGICA V3.2) ---
def calculate_projections(sessions_df, overrides_df):
    projections = []
    if sessions_df.empty:
        return pd.DataFrame()
    
    # Garante tipos corretos
    sessions_df['timestamp'] = pd.to_numeric(sessions_df['timestamp'], errors='coerce')
    sessions_df = sessions_df.dropna(subset=['timestamp'])
    
    # Agrupa por Assunto e ordena por tempo (Sliding Window)
    groups = sessions_df.sort_values('timestamp').groupby(['materia', 'assunto'])
    overrides_dict = pd.Series(overrides_df.date.values, index=overrides_df.id).to_dict() if not overrides_df.empty else {}

    for (materia, assunto), group in groups:
        latest = group.iloc[-1]
        initial = group.iloc[0]
        num = len(group)
        
        acc = (float(latest['acertos']) / float(latest['total'])) * 100
        initial_acc = (float(initial['acertos']) / float(initial['total'])) * 100
        
        # Data da última sessão como base (Sliding Window)
        try:
            last_dt = datetime.strptime(str(latest['data']), '%Y-%m-%d').date()
        except:
            last_dt = datetime.now().date()
            
        days = 1
        action, case_type, urgency = "", "", "low"
        
        # --- Lógica Condicional ABC ---
        if num > 1 and acc < 70:
            days, action, case_type, urgency = 1, "🚨 Rebaixado: Performance <70%. Refazer base do Caso A.", "Caso A - Rebaixado", "high"
        elif initial_acc < 70:
            if num == 1: days, action, case_type, urgency = 1, "D+1: Refazer erros (Foco 100% de acerto).", "Caso A - Resgate", "high"
            elif num == 2:
                if acc == 100: days, action, case_type, urgency = 3, "D+4: Teste de estabilidade (15 questões novas).", "Caso A - Estabilidade", "medium"
                else: days, action, case_type, urgency = 1, "⚠️ Repetir erros: Necessário 100% no D+1.", "Caso A - Repetir", "high"
            else:
                if acc > 85: days, action, case_type, urgency = 15, "✅ Promovido: Revisão de manutenção.", "Caso A -> C", "low"
                else: days, action, case_type, urgency = 7, "❌ Reforço: Revisão em 7 dias.", "Caso A -> B", "medium"
        elif initial_acc <= 85:
            if num == 1: days, action, case_type, urgency = 7, "D+7: Bateria mista (Objetivas + Discursivas).", "Caso B - Lapidação", "medium"
            else:
                if acc > 90: days, action, case_type, urgency = 30, "🔥 Maestria: Nota >90%. Próxima em 30 dias.", "Caso B -> C", "low"
                else: days, action, case_type, urgency = 14, "Fixação: Mantendo nível. Nova bateria em 14 dias.", "Caso B - Fixação", "medium"
        else:
            if acc < 80: days, action, case_type, urgency = 7, "📉 Queda: Nota <80%. Retorno para cronograma de 7 dias.", "Caso C -> B", "medium"
            elif num == 1: days, action, case_type, urgency = 15, "D+15: Simulado de tópicos focado em velocidade.", "Caso C - Maestria", "low"
            else: days, action, case_type, urgency = 45, "D+45: Manutenção Permanente.", "Caso C - Manutenção", "low"

        proj_dt = last_dt + timedelta(days=days)
        proj_str = proj_dt.strftime('%Y-%m-%d')
        
        # Override manual
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
    st.subheader("Cronograma de Revisões")
    proj_df = calculate_projections(df_sessions, df_overrides)
    
    if not proj_df.empty:
        proj_df = proj_df.sort_values('Data')
        
        # Filtro de Matéria na Agenda
        filtro_agenda = st.selectbox("Filtrar Agenda", ["Todas"] + SUBJECTS, key="filter_agenda")
        if filtro_agenda != "Todas":
            proj_df = proj_df[proj_df.Materia == filtro_agenda]

        for _, row in proj_df.iterrows():
            # Define cor baseada na urgência
            border_color = "#f43f5e" if row['Urgency'] == "high" else "#3b82f6"
            
            with st.expander(f"{row['Data']} | {row['Materia']} - {row['Assunto']}"):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(f"**Status:** {row['Caso']} (Sessão #{row['Passo']})")
                    st.markdown(f"**Última Performance:** {row['Nota']}")
                    st.info(f"👉 {row['Ação']}")
                    if row['Erros'] and str(row['Erros']) != "nan":
                        st.error(f"⚠️ Erros para refazer: {row['Erros']}")
                
                with c2:
                    # Ajuste de Data
                    new_date = st.date_input("Mudar data", value=datetime.strptime(row['Data'], '%Y-%m-%d'), key=f"date_{row['Key']}")
                    if new_date.strftime('%Y-%m-%d') != row['Data']:
                        new_ov = pd.DataFrame([{'id': row['Key'], 'date': new_date.strftime('%Y-%m-%d')}])
                        df_overrides = df_overrides[df_overrides.id != row['Key']] if not df_overrides.empty else df_overrides
                        df_overrides = pd.concat([df_overrides, new_ov], ignore_index=True)
                        save_to_sheets(df_sessions, df_overrides)
                        st.rerun()
                    
                    if st.button("Iniciar Estudo", key=f"btn_{row['Key']}"):
                        st.session_state.prefill = row
                        st.success("Copiado! Vá para 'Registrar'.")
    else:
        st.write("Nada agendado para os próximos dias.")

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
            t_input = st.number_input("Questões Totais", min_value=1, value=20)
        with c4:
            ac_input = st.number_input("Número de Acertos", min_value=0, value=0)
            
        err_input = st.text_area("Quais questões você errou?", help="Ex: Q01, Q05, Q10", placeholder="Deixe em branco se não houver erros")
        
        if st.form_submit_button("Salvar e Projetar"):
            new_row = pd.DataFrame([{
                'data': d_input.strftime('%Y-%m-%d'), 'materia': m_input, 'assunto': a_input,
                'total': int(t_input), 'acertos': int(ac_input), 'timestamp': datetime.now().timestamp(),
                'erros': err_input
            }])
            df_sessions = pd.concat([df_sessions, new_row], ignore_index=True)
            
            # Limpa override ao avançar no ciclo
            key = f"{m_input}-{a_input}".lower().replace(" ", "").replace("/", "-")
            df_overrides = df_overrides[df_overrides.id != key] if not df_overrides.empty else df_overrides
            
            save_to_sheets(df_sessions, df_overrides)
            st.session_state.prefill = None
            st.success("Sessão registrada com sucesso!")
            st.rerun()

with tabs[2]: # DESEMPENHO
    st.subheader("Análise de Performance")
    if not df_sessions.empty:
        df_sessions['total'] = pd.to_numeric(df_sessions['total'])
        df_sessions['acertos'] = pd.to_numeric(df_sessions['acertos'])
        df_sessions['nota'] = (df_sessions['acertos'] / df_sessions['total']) * 100
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Aproveitamento Médio", f"{df_sessions['nota'].mean():.1f}%")
        m2.metric("Total de Exercícios", int(df_sessions['total'].sum()))
        m3.metric("Assuntos Mapeados", len(df_sessions.groupby(['materia', 'assunto'])))
        
        st.markdown("---")
        st.markdown("#### Precisão por Matéria")
        subj_data = df_sessions.groupby('materia')['nota'].mean().reindex(SUBJECTS).fillna(0).reset_index()
        st.bar_chart(subj_data.set_index('materia'))
    else:
        st.info("Registre seus primeiros estudos para ver os gráficos de progresso.")

with tabs[3]: # HISTÓRICO
    st.subheader("Histórico Geral")
    if not df_sessions.empty:
        f_hist = st.selectbox("Filtrar Histórico", ["Todas"] + SUBJECTS)
        df_view = df_sessions.copy()
        if f_hist != "Todas":
            df_view = df_view[df_view.materia == f_hist]
            
        st.dataframe(df_view.sort_values('timestamp', ascending=False), hide_index=True, use_container_width=True)
        
        if st.checkbox("Habilitar Exclusão"):
            idx_del = st.number_input("ID da linha para apagar (ver índice)", min_value=0, max_value=len(df_sessions)-1, step=1)
            if st.button("Confirmar Exclusão Permanente"):
                df_sessions = df_sessions.drop(df_sessions.index[idx_del])
                save_to_sheets(df_sessions, df_overrides)
                st.rerun()

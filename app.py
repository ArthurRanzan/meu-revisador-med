import React, { useState, useEffect, useMemo } from 'react';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell 
} from 'recharts';
import { 
  PlusCircle, BookOpen, CheckCircle, Target, AlertCircle, 
  Calendar as CalendarIcon, Trash2, Trophy, Brain, Filter, Lock, Clock, ListChecks,
  X, Edit3, Save, AlertTriangle, Plus, ArrowRight, ChevronLeft, ChevronRight,
  BarChart3, History, LayoutDashboard
} from 'lucide-react';
import { initializeApp } from 'firebase/app';
import { 
  getFirestore, collection, addDoc, onSnapshot, 
  query, orderBy, deleteDoc, doc, updateDoc, setDoc, deleteField
} from 'firebase/firestore';
import { 
  getAuth, signInAnonymously, onAuthStateChanged, signInWithCustomToken 
} from 'firebase/auth';

const firebaseConfig = JSON.parse(__firebase_config);
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);
const appId = typeof __app_id !== 'undefined' ? __app_id : 'med-track-uel-ufpr';

const DISCURSIVE_SUBJECTS = ["Biologia", "Química", "Filosofia/Sociologia", "Gramática", "Literatura"];
const SUBJECTS = ["Biologia", "Química", "Física", "Matemática", "Gramática", "Literatura", "História", "Geografia", "Filosofia/Sociologia", "Inglês", "Redação"];
const ERROR_TYPES = ["Falta de Conteúdo", "Interpretação", "Atenção/Distração", "Tempo Insuficiente", "Cálculo/Sinal", "Pegadinha"];

// Função robusta para data local YYYY-MM-DD
const getLocalDateString = (date = new Date()) => {
  const d = new Date(date);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const App = () => {
  const [user, setUser] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [overrides, setOverrides] = useState({}); 
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('agenda'); 
  const [agendaMode, setAgendaMode] = useState('calendar'); 
  const [selectedSession, setSelectedSession] = useState(null);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedCalendarDate, setSelectedCalendarDate] = useState(getLocalDateString());
  const [filterSubject, setFilterSubject] = useState('Todas');

  const [formData, setFormData] = useState({
    subject: SUBJECTS[0],
    topic: '',
    total: '',
    correct: '',
    isDiscursive: false,
    date: getLocalDateString(),
    wrongQuestions: [] 
  });

  useEffect(() => {
    const initAuth = async () => {
      try {
        if (typeof __initial_auth_token !== 'undefined' && __initial_auth_token) {
          await signInWithCustomToken(auth, __initial_auth_token);
        } else {
          await signInAnonymously(auth);
        }
      } catch (err) { console.error(err); }
    };
    initAuth();
    const unsubscribe = onAuthStateChanged(auth, setUser);
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (!user) return;
    const qSessions = query(collection(db, 'artifacts', appId, 'users', user.uid, 'sessions'), orderBy('date', 'asc'));
    const unsubSessions = onSnapshot(qSessions, (snapshot) => {
      setSessions(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
    });
    const qOverrides = query(collection(db, 'artifacts', appId, 'users', user.uid, 'overrides'));
    const unsubOverrides = onSnapshot(qOverrides, (snapshot) => {
      const data = {};
      snapshot.docs.forEach(doc => { data[doc.id] = doc.data().date; });
      setOverrides(data);
      setLoading(false);
    });
    return () => { unsubSessions(); unsubOverrides(); };
  }, [user]);

  // ENGINE DE MÉTRICAS (PROXIMAS REVISÕES + PROGRESSO)
  const statsMetrics = useMemo(() => {
    const data = {
      totalQ: 0,
      totalC: 0,
      bySubject: {},
      casesCount: { A: 0, B: 0, C: 0 },
      projections: []
    };

    const topicsGroups = {};
    sessions.forEach(s => {
      const key = `${s.subject}-${s.topic.toLowerCase().trim()}`;
      if (!topicsGroups[key]) topicsGroups[key] = [];
      topicsGroups[key].push(s);
      
      data.totalQ += (parseInt(s.total) || 0);
      data.totalC += (parseInt(s.correct) || 0);
      
      if (!data.bySubject[s.subject]) data.bySubject[s.subject] = { q: 0, c: 0 };
      data.bySubject[s.subject].q += (parseInt(s.total) || 0);
      data.bySubject[s.subject].c += (parseInt(s.correct) || 0);
    });

    Object.keys(topicsGroups).forEach(key => {
      const topicSessions = [...topicsGroups[key]].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
      const latestSession = topicSessions[topicSessions.length - 1];
      const initialSession = topicSessions[0];
      const latestAccuracy = (latestSession.correct / latestSession.total) * 100;
      const initialAccuracy = (initialSession.correct / initialSession.total) * 100;
      const numSessions = topicSessions.length;
      
      const [ly, lm, ld] = latestSession.date.split('-').map(Number);
      const lastSessionDate = new Date(ly, lm - 1, ld, 12, 0, 0);

      if (initialAccuracy < 70) data.casesCount.A++;
      else if (initialAccuracy <= 85) data.casesCount.B++;
      else data.casesCount.C++;

      const addProj = (daysFromLast, action, type, urgency) => {
        const targetDate = new Date(lastSessionDate);
        targetDate.setDate(targetDate.getDate() + (daysFromLast || 1));
        let projDateStr = getLocalDateString(targetDate);
        const overrideKey = `${latestSession.subject}-${latestSession.topic.toLowerCase().trim()}`.replace(/\//g, '-');
        if (overrides[overrideKey]) projDateStr = overrides[overrideKey];

        data.projections.push({
          date: projDateStr,
          subject: latestSession.subject,
          topic: latestSession.topic,
          action, type, urgency,
          accuracy: latestAccuracy,
          step: numSessions,
          overrideKey,
          wrongQuestions: latestSession.wrongQuestions || []
        });
      };

      if (numSessions > 1 && latestAccuracy < 70) {
        addProj(1, "🚨 Rebaixado: Performance <70%. Reiniciar base Caso A.", "Caso A - Rebaixado", "high");
      } else if (initialAccuracy < 70) {
        if (numSessions === 1) addProj(1, "D+1: Refazer erros. Foco caderno de erros.", "Caso A - Resgate", "high");
        else if (numSessions === 2) {
          if (latestAccuracy === 100) addProj(3, "D+4: Teste de Estabilidade.", "Caso A - Estabilidade", "medium");
          else addProj(1, "⚠️ Falha no D+1: Repetir erros da última sessão.", "Caso A - Repetir D+1", "high");
        } else if (numSessions === 3) {
          if (latestAccuracy > 85) addProj(15, "✅ Promovido: Revisão em 15 dias.", "Caso A -> C", "low");
          else addProj(7, "❌ Reforço: Abaixo de 85%. Revisão em 7 dias.", "Caso A -> B", "medium");
        } else addProj(30, "Manutenção Permanente.", "Manutenção", "low");
      } else if (initialAccuracy <= 85) {
        if (numSessions === 1) addProj(7, "D+7: Bateria mista (Obj+Disc).", "Caso B - Lapidação", "medium");
        else {
          if (latestAccuracy > 90) addProj(30, "🔥 Maestria Alcançada: Próxima em 30 dias.", "Caso B -> C", "low");
          else addProj(14, "Fixação: Manutenção em 14 dias.", "Caso B - Fixação", "medium");
        }
      } else {
        if (latestAccuracy < 80) addProj(7, "📉 Queda (<80%): Retorno para ciclo de 7 dias.", "Caso C -> B", "medium");
        else if (numSessions === 1) addProj(15, "D+15: Simulado de tópicos rápido.", "Caso C - Maestria", "low");
        else addProj(45, "D+45: Manutenção Longo Prazo.", "Caso C - Manutenção", "low");
      }
    });

    return data;
  }, [sessions, overrides]);

  const calendarDays = useMemo(() => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const firstDay = new Date(year, month, 1).getDay();
    const lastDate = new Date(year, month + 1, 0).getDate();
    
    const days = [];
    for (let i = 0; i < firstDay; i++) days.push({ day: null });
    for (let i = 1; i <= lastDate; i++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(i).padStart(2, '0')}`;
      const tasks = statsMetrics.projections.filter(r => r.date === dateStr);
      days.push({ day: i, date: dateStr, tasks });
    }
    return days;
  }, [currentDate, statsMetrics.projections]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!user || !formData.total || !formData.topic) return;
    try {
      await addDoc(collection(db, 'artifacts', appId, 'users', user.uid, 'sessions'), {
        ...formData,
        total: parseInt(formData.total),
        correct: parseInt(formData.correct),
        timestamp: new Date().getTime()
      });
      const key = `${formData.subject}-${formData.topic.toLowerCase().trim()}`.replace(/\//g, '-');
      await setDoc(doc(db, 'artifacts', appId, 'users', user.uid, 'overrides', key), { date: deleteField() }, { merge: true });
      setFormData({ subject: SUBJECTS[0], topic: '', total: '', correct: '', isDiscursive: false, date: getLocalDateString(), wrongQuestions: [] });
      setView('agenda');
    } catch (err) { console.error(err); }
  };

  if (loading) return <div className="h-screen bg-slate-950 flex items-center justify-center"><div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full"></div></div>;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans p-4 md:p-8">
      {/* Modal de Detalhes */}
      {selectedSession && (
        <div className="fixed inset-0 bg-slate-950/90 backdrop-blur-md z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 w-full max-w-xl rounded-3xl overflow-hidden shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="p-6 border-b border-slate-800 flex justify-between items-center bg-slate-900/50">
              <div>
                <h3 className="text-xl font-bold">{selectedSession.topic}</h3>
                <p className="text-xs text-blue-400 font-bold uppercase tracking-widest">{selectedSession.subject}</p>
              </div>
              <button onClick={() => setSelectedSession(null)} className="p-2 hover:bg-slate-800 rounded-full transition"><X size={20}/></button>
            </div>
            <div className="p-6 space-y-6 overflow-y-auto max-h-[70vh]">
              <div className="grid grid-cols-3 gap-3">
                 <div className="p-4 bg-slate-950 rounded-2xl border border-slate-800 text-center">
                    <p className="text-[10px] text-slate-500 font-bold uppercase mb-1">Nota</p>
                    <p className="text-2xl font-black">{selectedSession.accuracy ? selectedSession.accuracy.toFixed(0) : '0'}%</p>
                 </div>
                 <div className="p-4 bg-slate-950 rounded-2xl border border-slate-800 text-center">
                    <p className="text-[10px] text-slate-500 font-bold uppercase mb-1">Sessão</p>
                    <p className="text-2xl font-black text-blue-400">#{selectedSession.step || '1'}</p>
                 </div>
                 <div className="p-4 bg-slate-950 rounded-2xl border border-slate-800 text-center">
                    <p className="text-[10px] text-slate-500 font-bold uppercase mb-1">Ciclo</p>
                    <p className="text-[10px] font-black text-emerald-400 mt-2 uppercase">{selectedSession.type ? selectedSession.type.split(' - ')[0] : 'Novo'}</p>
                 </div>
              </div>
              {selectedSession.wrongQuestions?.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-[10px] font-black uppercase text-rose-500 tracking-widest flex items-center gap-2"><AlertTriangle size={14} /> Caderno de Erros:</h4>
                  <div className="grid grid-cols-1 gap-2">
                    {selectedSession.wrongQuestions.map((q, idx) => (
                      <div key={idx} className="p-3 bg-slate-950 border border-slate-800 rounded-xl flex justify-between items-center">
                        <span className="font-bold text-sm text-slate-200">{q.ref || `Q${idx + 1}`}</span>
                        <span className="text-[10px] bg-rose-500/10 text-rose-500 px-2 py-0.5 rounded font-bold uppercase">{q.type}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="space-y-3">
                 <label className="text-[10px] font-black uppercase text-slate-500 tracking-widest flex items-center gap-2"><CalendarIcon size={14} className="text-amber-500" /> Mover para outro dia</label>
                 <div className="flex gap-2">
                    <input type="date" value={selectedSession.date} onChange={(e) => {
                      const key = selectedSession.overrideKey || `${selectedSession.subject}-${selectedSession.topic.toLowerCase().trim()}`.replace(/\//g, '-');
                      setDoc(doc(db, 'artifacts', appId, 'users', user.uid, 'overrides', key), { date: e.target.value });
                      setSelectedSession({...selectedSession, date: e.target.value});
                    }} className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-amber-500 transition-all" />
                 </div>
              </div>
              <div className="bg-blue-600/10 border border-blue-500/20 p-5 rounded-2xl">
                <h4 className="text-[10px] font-black uppercase text-blue-400 mb-2 tracking-widest">O que fazer hoje:</h4>
                <p className="text-sm text-slate-200 leading-relaxed italic">"{selectedSession.action || 'Continuar estudos.'}"</p>
              </div>
            </div>
            <div className="p-6 border-t border-slate-800 flex gap-3">
              <button onClick={() => setSelectedSession(null)} className="flex-1 bg-slate-800 hover:bg-slate-700 py-4 rounded-2xl font-bold text-xs uppercase transition-all">Fechar</button>
              <button onClick={() => {
                setFormData({...formData, subject: selectedSession.subject, topic: selectedSession.topic, date: getLocalDateString()});
                setView('log');
                setSelectedSession(null);
              }} className="flex-[2] bg-blue-600 hover:bg-blue-500 py-4 rounded-2xl font-black text-xs shadow-xl flex items-center justify-center gap-2 uppercase transition-all"><ArrowRight size={16}/> Iniciar Registro</button>
            </div>
          </div>
        </div>
      )}

      {/* Header Atualizado */}
      <header className="max-w-6xl mx-auto flex flex-col md:flex-row justify-between items-center mb-10 gap-4">
        <div onClick={() => setView('agenda')} className="cursor-pointer">
          <h1 className="text-4xl font-black bg-gradient-to-r from-blue-400 via-cyan-300 to-emerald-400 bg-clip-text text-transparent italic tracking-tighter">REVISADOR</h1>
        </div>
        <nav className="flex bg-slate-900/50 p-1 rounded-2xl border border-slate-800 shadow-xl overflow-x-auto max-w-full">
          <button onClick={() => setView('agenda')} className={`px-5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${view === 'agenda' ? 'bg-blue-600 shadow-lg' : 'hover:bg-slate-800'}`}><CalendarIcon size={14}/> Agenda</button>
          <button onClick={() => setView('log')} className={`px-5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${view === 'log' ? 'bg-blue-600 shadow-lg' : 'hover:bg-slate-800'}`}><PlusCircle size={14}/> Registrar</button>
          <button onClick={() => setView('stats')} className={`px-5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${view === 'stats' ? 'bg-blue-600 shadow-lg' : 'hover:bg-slate-800'}`}><BarChart3 size={14}/> Desempenho</button>
          <button onClick={() => setView('history')} className={`px-5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 whitespace-nowrap ${view === 'history' ? 'bg-blue-600 shadow-lg' : 'hover:bg-slate-800'}`}><History size={14}/> Histórico</button>
        </nav>
      </header>

      <main className="max-w-6xl mx-auto">
        {view === 'agenda' && (
          <div className="space-y-6 animate-in fade-in duration-300">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-black flex items-center gap-2"><Clock className="text-blue-400" /> Fluxo de Estudos</h2>
              <div className="flex bg-slate-900 p-1 rounded-xl border border-slate-800">
                <button onClick={() => setAgendaMode('calendar')} className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase transition ${agendaMode === 'calendar' ? 'bg-slate-700 text-white' : 'text-slate-500'}`}>Calendário</button>
                <button onClick={() => setAgendaMode('list')} className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase transition ${agendaMode === 'list' ? 'bg-slate-700 text-white' : 'text-slate-500'}`}>Lista</button>
              </div>
            </div>

            {agendaMode === 'calendar' ? (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-xl h-fit">
                  <div className="flex items-center justify-between mb-8">
                    <h3 className="font-black text-xl uppercase tracking-tighter text-blue-400">{currentDate.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })}</h3>
                    <div className="flex gap-2">
                      <button onClick={() => setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1))} className="p-2 hover:bg-slate-800 rounded-xl transition"><ChevronLeft size={24}/></button>
                      <button onClick={() => setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1))} className="p-2 hover:bg-slate-800 rounded-xl transition"><ChevronRight size={24}/></button>
                    </div>
                  </div>
                  <div className="grid grid-cols-7 gap-2 mb-4 text-center text-[10px] font-black text-slate-600 uppercase tracking-widest">
                    {['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].map(d => <div key={d}>{d}</div>)}
                  </div>
                  <div className="grid grid-cols-7 gap-2">
                    {calendarDays.map((d, i) => (
                      <div key={i} onClick={() => d.day && setSelectedCalendarDate(d.date)} className={`aspect-square rounded-2xl border p-1 flex flex-col items-center justify-center relative cursor-pointer transition-all duration-200 ${!d.day ? 'border-transparent opacity-0 pointer-events-none' : selectedCalendarDate === d.date ? 'border-blue-500 bg-blue-500/10 scale-105 z-10' : 'border-slate-800 hover:border-slate-600 bg-slate-950/50 shadow-sm'}`}>
                        <span className={`text-xs font-bold ${selectedCalendarDate === d.date ? 'text-blue-400' : 'text-slate-500'}`}>{d.day}</span>
                        {d.tasks?.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1 justify-center">
                            {d.tasks.map((t, idx) => (
                              <div key={idx} className={`w-1.5 h-1.5 rounded-full ${t.urgency === 'high' ? 'bg-rose-500 animate-pulse' : t.urgency === 'medium' ? 'bg-amber-400' : 'bg-blue-400'}`} />
                            ))}
                          </div>
                        )}
                        {d.date === getLocalDateString() && <div className="absolute top-1 right-1 w-1.5 h-1.5 bg-white rounded-full shadow-glow" />}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="space-y-4">
                   <h3 className="font-black text-slate-400 text-xs uppercase tracking-widest flex items-center gap-2 mb-4"><CalendarIcon size={16} className="text-blue-400" />{new Date(selectedCalendarDate + 'T12:00:00').toLocaleDateString('pt-BR', { day: 'numeric', month: 'long' })}</h3>
                   <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2 custom-scrollbar">
                     {statsMetrics.projections.filter(item => item.date === selectedCalendarDate).map((item, i) => (
                       <div key={i} className="p-5 rounded-2xl border bg-slate-900 border-slate-800 hover:border-blue-500 transition-all cursor-pointer group shadow-lg" onClick={() => setSelectedSession(item)}>
                          <div className="flex justify-between items-start mb-3">
                             <span className={`text-[8px] font-black px-2 py-0.5 rounded uppercase tracking-tighter ${item.urgency === 'high' ? 'bg-rose-500/20 text-rose-400' : 'bg-blue-500/20 text-blue-400'}`}>{item.type}</span>
                             <ArrowRight size={14} className="text-slate-700 group-hover:text-blue-400 transition-colors" />
                          </div>
                          <h4 className="font-bold text-sm mb-1">{item.topic}</h4>
                          <p className="text-[10px] text-slate-500 font-black mb-4 uppercase tracking-tighter">{item.subject}</p>
                          <div className="text-[11px] text-slate-300 leading-relaxed bg-slate-950 p-4 rounded-xl border border-slate-800 italic">"{item.action}"</div>
                       </div>
                     ))}
                     {statsMetrics.projections.filter(item => item.date === selectedCalendarDate).length === 0 && (
                       <div className="text-center py-24 bg-slate-900/40 rounded-3xl border border-dashed border-slate-800 flex flex-col items-center gap-3">
                          <Brain size={32} className="text-slate-800" /><p className="text-xs text-slate-600 font-bold uppercase tracking-widest">Nada agendado</p>
                       </div>
                     )}
                   </div>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {[...statsMetrics.projections].sort((a,b) => a.date.localeCompare(b.date)).map((item, i) => (
                  <div key={i} className="p-5 rounded-3xl border bg-slate-900/40 border-slate-800 hover:border-blue-500 transition-all cursor-pointer group shadow-lg" onClick={() => setSelectedSession(item)}>
                    <div className="flex justify-between items-start mb-3">
                      <span className="text-[9px] px-2 py-0.5 rounded-lg font-black uppercase bg-slate-800 text-slate-400 tracking-tighter">{new Date(item.date + 'T12:00:00').toLocaleDateString('pt-BR')}</span>
                      <span className="text-[9px] font-black text-blue-400 uppercase tracking-tighter">{item.type}</span>
                    </div>
                    <h3 className="font-bold text-lg mb-1 truncate">{item.topic}</h3>
                    <p className="text-xs text-slate-500 font-medium mb-4">{item.subject}</p>
                    <div className="p-3 bg-slate-950 rounded-xl border border-slate-800/50 text-[10px] text-slate-400 italic">"{item.action}"</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* VIEW: LOG */}
        {view === 'log' && (
          <div className="max-w-2xl mx-auto bg-slate-900 border border-slate-800 rounded-3xl p-8 shadow-2xl animate-in fade-in duration-300">
            <h2 className="text-3xl font-black mb-8 tracking-tighter italic">Novo Registro</h2>
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest px-1">Matéria</label>
                  <select value={formData.subject} onChange={e => setFormData({...formData, subject: e.target.value})} className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-4 text-sm outline-none focus:ring-2 focus:ring-blue-500 transition-all">
                    {SUBJECTS.map(s => <option key={s} value={s}>{s} {DISCURSIVE_SUBJECTS.includes(s) ? '★' : ''}</option>)}
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest px-1">Data</label>
                  <input type="date" value={formData.date} onChange={e => setFormData({...formData, date: e.target.value})} className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-4 text-sm outline-none" />
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest px-1">O que você estudou hoje?</label>
                <input placeholder="Ex: Citologia, Estequiometria..." value={formData.topic} onChange={e => setFormData({...formData, topic: e.target.value})} className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-4 text-sm outline-none focus:ring-2 focus:ring-blue-500 transition-all font-medium" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest px-1">Questões Totais</label>
                  <input type="number" placeholder="0" value={formData.total} onChange={e => setFormData({...formData, total: e.target.value})} className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-4 text-sm outline-none" />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest px-1">Acertos</label>
                  <input type="number" placeholder="0" value={formData.correct} onChange={e => setFormData({...formData, correct: e.target.value})} className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-4 text-sm outline-none" />
                </div>
              </div>
              <div className="space-y-4 pt-4 border-t border-slate-800">
                <div className="flex items-center justify-between">
                  <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Registrar Erros (Opcional)</h4>
                  <button type="button" onClick={() => setFormData({...formData, wrongQuestions: [...formData.wrongQuestions, { id: Date.now(), ref: '', type: ERROR_TYPES[2] }]})} className="flex items-center gap-1 text-[9px] font-black bg-slate-800 hover:bg-blue-600 px-3 py-1.5 rounded-lg transition-all shadow-sm"><Plus size={12} /> Adicionar Erro</button>
                </div>
                <div className="space-y-3">
                  {formData.wrongQuestions.map((q) => (
                    <div key={q.id} className="grid grid-cols-12 gap-2 animate-in slide-in-from-right-2">
                      <div className="col-span-4"><input placeholder="Ref (ex: Q01)" value={q.ref} onChange={(e) => setFormData({...formData, wrongQuestions: formData.wrongQuestions.map(wq => wq.id === q.id ? {...wq, ref: e.target.value} : wq)})} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs outline-none focus:border-blue-500" /></div>
                      <div className="col-span-7"><select value={q.type} onChange={(e) => setFormData({...formData, wrongQuestions: formData.wrongQuestions.map(wq => wq.id === q.id ? {...wq, type: e.target.value} : wq)})} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs outline-none">{ERROR_TYPES.map(t => <option key={t} value={t}>{t}</option>)}</select></div>
                      <div className="col-span-1 flex items-center justify-end"><button type="button" onClick={() => setFormData({...formData, wrongQuestions: formData.wrongQuestions.filter(wq => wq.id !== q.id)})} className="text-slate-600 hover:text-rose-500 transition"><X size={16}/></button></div>
                    </div>
                  ))}
                </div>
              </div>
              <button type="submit" className="w-full bg-blue-600 hover:bg-blue-500 py-5 rounded-2xl font-black text-sm shadow-xl shadow-blue-900/30 transition-all uppercase tracking-widest">Salvar Sessão & Gerar Ciclo</button>
            </form>
          </div>
        )}

        {/* VIEW: DESEMPENHO */}
        {view === 'stats' && (
          <div className="space-y-8 animate-in fade-in duration-500">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-slate-900 border border-slate-800 p-6 rounded-3xl">
                <div className="text-slate-500 text-[10px] font-black uppercase mb-1">Questões Totais</div>
                <div className="text-3xl font-black text-blue-400">{statsMetrics.totalQ}</div>
              </div>
              <div className="bg-slate-900 border border-slate-800 p-6 rounded-3xl">
                <div className="text-slate-500 text-[10px] font-black uppercase mb-1">Aproveitamento</div>
                <div className="text-3xl font-black text-emerald-400">{((statsMetrics.totalC / statsMetrics.totalQ) * 100 || 0).toFixed(1)}%</div>
              </div>
              <div className="bg-slate-900 border border-slate-800 p-6 rounded-3xl">
                <div className="text-slate-500 text-[10px] font-black uppercase mb-1">Em Maestria</div>
                <div className="text-3xl font-black text-purple-400">{statsMetrics.casesCount.C}</div>
              </div>
              <div className="bg-slate-900 border border-slate-800 p-6 rounded-3xl">
                <div className="text-slate-500 text-[10px] font-black uppercase mb-1">Em Resgate</div>
                <div className="text-3xl font-black text-rose-500">{statsMetrics.casesCount.A}</div>
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-3xl p-8 shadow-xl">
               <div className="flex items-center justify-between mb-8">
                  <h3 className="text-xl font-black italic tracking-tighter flex items-center gap-2"><LayoutDashboard className="text-blue-400" /> Precisão por Matéria</h3>
               </div>
               <div className="h-80 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={Object.entries(statsMetrics.bySubject).map(([name, s]) => ({ name, accuracy: (s.c / s.q) * 100 }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                      <XAxis dataKey="name" stroke="#64748b" fontSize={10} axisLine={false} tickLine={false} />
                      <YAxis stroke="#64748b" fontSize={10} axisLine={false} tickLine={false} unit="%" />
                      <Tooltip cursor={{fill: '#1e293b', radius: 8}} contentStyle={{ backgroundColor: '#0f172a', border: 'none', borderRadius: '12px', color: '#f1f5f9' }} />
                      <Bar dataKey="accuracy" radius={[8, 8, 0, 0]} barSize={40}>
                        {Object.entries(statsMetrics.bySubject).map((entry, index) => {
                          const acc = (entry[1].c / entry[1].q) * 100;
                          return <Cell key={`cell-${index}`} fill={acc < 70 ? '#f43f5e' : acc <= 85 ? '#fbbf24' : '#10b981'} />;
                        })}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
               </div>
            </div>
          </div>
        )}

        {/* VIEW: HISTÓRICO */}
        {view === 'history' && (
          <div className="space-y-6 animate-in fade-in duration-300">
            <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 flex flex-col md:flex-row justify-between items-center gap-4">
                <div className="flex items-center gap-3">
                    <Filter size={20} className="text-blue-400" />
                    <h3 className="font-bold uppercase tracking-widest text-xs text-slate-400">Filtrar:</h3>
                    <select value={filterSubject} onChange={e => setFilterSubject(e.target.value)} className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs outline-none">
                        <option value="Todas">Todas as Matérias</option>
                        {SUBJECTS.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                </div>
            </div>
            <div className="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-xl">
               <div className="overflow-x-auto">
                 <table className="w-full text-left text-xs">
                   <thead className="bg-slate-950 text-slate-500 uppercase tracking-tighter">
                     <tr>
                       <th className="p-5">Data</th>
                       <th className="p-5">Assunto</th>
                       <th className="p-5">Matéria</th>
                       <th className="p-5 text-center">Erros</th>
                       <th className="p-5">Nota</th>
                       <th className="p-5"></th>
                     </tr>
                   </thead>
                   <tbody className="divide-y divide-slate-800">
                     {[...sessions]
                        .filter(s => filterSubject === 'Todas' || s.subject === filterSubject)
                        .reverse().map(s => {
                         const acc = (s.correct/s.total)*100;
                         return (
                           <tr key={s.id} className="hover:bg-slate-800/20 group transition">
                             <td className="p-5 text-slate-500 font-mono">{s.date}</td>
                             <td className="p-5 font-bold cursor-pointer" onClick={() => {
                               setSelectedSession({...s, accuracy: acc, type: acc < 70 ? 'Caso A' : acc <= 85 ? 'Caso B' : 'Caso C', action: "Visualização Histórica", step: sessions.filter(x => x.topic.toLowerCase() === s.topic.toLowerCase()).length});
                             }}>{s.topic}</td>
                             <td className="p-5 text-slate-400">{s.subject}</td>
                             <td className="p-5 text-center">
                                {s.wrongQuestions?.length > 0 ? (
                                  <span className="bg-rose-500/10 text-rose-500 px-2 py-1 rounded text-[9px] font-black">{s.wrongQuestions.length} QUESTÕES</span>
                                ) : '-'}
                             </td>
                             <td className={`p-5 font-black text-sm ${acc >= 80 ? 'text-emerald-400' : 'text-rose-400'}`}>{acc.toFixed(0)}%</td>
                             <td className="p-5 text-right">
                               <button onClick={() => deleteDoc(doc(db, 'artifacts', appId, 'users', user.uid, 'sessions', s.id))} className="text-slate-700 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition"><Trash2 size={16}/></button>
                             </td>
                           </tr>
                         );
                       })}
                   </tbody>
                 </table>
               </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default App;

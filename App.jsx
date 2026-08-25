import React, { useState } from 'react';
import { ShieldAlert, Bot, Database, FileText, BarChart3, X, Send, UploadCloud, Lock, AlertTriangle } from 'lucide-react';

const API_BASE_URL = "http://localhost:8000/api/v1";

export default function App() {
  const [activeTab, setActiveTab] = useState('copilot');
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [userRole, setUserRole] = useState('analyst');
  
  const [fileToUpload, setFileToUpload] = useState(null);
  const [uploadStatus, setUploadStatus] = useState('');

  // États pour le Copilot SQL
  const [sqlPrompt, setSqlPrompt] = useState('');
  const [sqlResult, setSqlResult] = useState(null);
  const [sqlLoading, setSqlLoading] = useState(false);

  const [messages, setMessages] = useState([
    { role: 'assistant', text: 'Bonjour ! Je suis connecté à votre infrastructure GCP. Comment puis-je vous aider ?' }
  ]);
  const [inputMessage, setInputMessage] = useState('');

  const handleUpload = async () => {
    if (!fileToUpload) return;
    setUploadStatus('Sauvegarde dans Google Cloud Storage & Indexation...');
    
    const formData = new FormData();
    formData.append('file', fileToUpload);
    formData.append('required_role', userRole);

    try {
      const res = await fetch(`${API_BASE_URL}/upload-doc`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (res.ok) {
        setUploadStatus(`✅ Sauvegardé dans GCP : ${data.gcs_uri}`);
      } else {
        setUploadStatus(`❌ Erreur : ${data.detail}`);
      }
    } catch (err) {
      setUploadStatus('❌ Erreur de connexion avec l API');
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim()) return;

    const userText = inputMessage;
    setMessages(prev => [...prev, { role: 'user', text: userText }]);
    setInputMessage('');

    try {
      const res = await fetch(`${API_BASE_URL}/rag-chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: userText, user_role: userRole })
      });
      const data = await res.json();
      setMessages(prev => [...prev, { role: 'assistant', text: data.response }]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', text: '⚠️ Impossible de joindre le serveur API.' }]);
    }
  };

  const handleSqlSubmit = async (e) => {
    e.preventDefault();
    if (!sqlPrompt.trim()) return;

    setSqlLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/copilot-sql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: sqlPrompt, user_role: userRole })
      });
      const data = await res.json();
      setSqlResult(data.result);
    } catch (err) {
      setSqlResult({ type: 'error', message: 'Erreur de connexion avec le serveur SQL' });
    } finally {
      setSqlLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans">
      
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur sticky top-0 z-40 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-600/20 text-blue-400 rounded-xl border border-blue-500/30">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">Plateforme Anti-Fraude <span className="text-blue-500">GCP Native</span></h1>
            <p className="text-xs text-slate-400">Connected to Cloud SQL & Google Cloud Storage</p>
          </div>
        </div>

        <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5">
          <Lock className="w-4 h-4 text-blue-400" />
          <span className="text-xs text-slate-400">Droits :</span>
          <select value={userRole} onChange={(e) => setUserRole(e.target.value)} className="bg-transparent text-sm font-semibold text-blue-400 focus:outline-none cursor-pointer">
            <option value="analyst" className="bg-slate-900 text-white">Analyst</option>
            <option value="dg" className="bg-slate-900 text-white">DG</option>
            <option value="admin" className="bg-slate-900 text-white">Admin</option>
          </select>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        <div className="flex gap-2 border-b border-slate-800 pb-2">
          <button onClick={() => setActiveTab('copilot')} className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition ${activeTab === 'copilot' ? 'bg-blue-600 text-white' : 'text-slate-400'}`}><Database className="w-4 h-4" /> Copilot SQL</button>
          <button onClick={() => setActiveTab('rag')} className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition ${activeTab === 'rag' ? 'bg-blue-600 text-white' : 'text-slate-400'}`}><FileText className="w-4 h-4" /> Sauvegarde GCP & RAG</button>
          <button onClick={() => setActiveTab('alerts')} className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition ${activeTab === 'alerts' ? 'bg-blue-600 text-white' : 'text-slate-400'}`}><AlertTriangle className="w-4 h-4" /> Alertes</button>
          <button onClick={() => setActiveTab('dg')} className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition ${activeTab === 'dg' ? 'bg-blue-600 text-white' : 'text-slate-400'}`}><BarChart3 className="w-4 h-4" /> KPIs Décisionnels</button>
        </div>

        {/* Onglet Copilot SQL */}
        {activeTab === 'copilot' && (
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-6 space-y-6">
            <div>
              <h2 className="text-xl font-bold flex items-center gap-2">
                <Database className="w-5 h-5 text-blue-500" /> Copilot SQL & Analyse de Transactions
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Interrogez directement vos données structurées PostgreSQL en langage naturel.
              </p>
            </div>

            <form onSubmit={handleSqlSubmit} className="flex gap-3">
              <input 
                type="text" 
                placeholder="Ex: Donne-moi les dernières transactions suspectes..." 
                value={sqlPrompt} 
                onChange={(e) => setSqlPrompt(e.target.value)} 
                className="flex-1 bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-blue-500"
              />
              <button 
                type="submit" 
                disabled={sqlLoading}
                className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-3 rounded-xl text-sm font-semibold transition flex items-center gap-2"
              >
                {sqlLoading ? 'Analyse...' : 'Exécuter'}
              </button>
            </form>

            {/* Affichage des résultats sous forme de tableau */}
            {sqlResult && (
              <div className="mt-6 space-y-4">
                {sqlResult.type === 'error' ? (
                  <div className="p-4 bg-red-950/50 border border-red-800 text-red-200 rounded-xl text-sm">
                    {sqlResult.message}
                  </div>
                ) : (
                  <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900/40">
                    <div className="p-3 bg-slate-900 border-b border-slate-800 text-xs font-semibold text-slate-400">
                      Résultats de la base PostgreSQL ({sqlResult.data?.length || 0} lignes)
                    </div>
                    <div className="overflow-x-auto max-h-96">
                      <table className="w-full text-left text-xs text-slate-300">
                        <thead className="bg-slate-900 text-slate-400 uppercase font-mono sticky top-0">
                          <tr>
                            {sqlResult.columns?.map((col, index) => (
                              <th key={index} className="px-4 py-3 border-b border-slate-800">{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 font-mono">
                          {sqlResult.data?.length > 0 ? (
                            sqlResult.data.map((row, rowIndex) => (
                              <tr key={rowIndex} className="hover:bg-slate-800/40 transition">
                                {row.map((cell, cellIndex) => (
                                  <td key={cellIndex} className="px-4 py-2.5 whitespace-nowrap">{String(cell)}</td>
                                ))}
                              </tr>
                            ))
                          ) : (
                            <tr>
                              <td colSpan={sqlResult.columns?.length || 1} className="px-4 py-6 text-center text-slate-500">
                                Aucun résultat trouvé.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Onglet RAG & Stockage GCP */}
        {activeTab === 'rag' && (
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-6 space-y-4">
            <h2 className="text-xl font-bold">📤 Ajout de document (Google Cloud Storage)</h2>
            <div className="border-2 border-dashed border-slate-800 rounded-xl p-8 text-center bg-slate-900/50 space-y-4">
              <UploadCloud className="w-10 h-10 text-blue-400 mx-auto" />
              <input type="file" onChange={(e) => setFileToUpload(e.target.files[0])} className="block mx-auto text-sm text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-blue-600 file:text-white cursor-pointer" />
              <button onClick={handleUpload} className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2 rounded-lg text-sm font-semibold transition">Sauvegarder dans GCP Storage</button>
              {uploadStatus && <p className="text-xs font-mono text-blue-400 mt-2">{uploadStatus}</p>}
            </div>
          </div>
        )}
      </main>

      {isChatOpen && (
        <div className="fixed bottom-24 right-6 w-96 h-[480px] bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl flex flex-col z-50 overflow-hidden">
          <div className="bg-slate-900 border-b border-slate-800 p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-600 text-white rounded-lg"><Bot className="w-5 h-5" /></div>
              <div>
                <h3 className="text-sm font-bold">Assistant IA Anti-Fraude</h3>
                <span className="text-[10px] text-green-400 flex items-center gap-1"><span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse"></span> Connecté à l'API</span>
              </div>
            </div>
            <button onClick={() => setIsChatOpen(false)} className="text-slate-400 hover:text-white"><X className="w-5 h-5" /></button>
          </div>

          <div className="flex-1 p-4 overflow-y-auto space-y-3 bg-slate-900/30 text-sm">
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] p-3 rounded-2xl ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-200 border border-slate-700'}`}>
                  {msg.text}
                </div>
              </div>
            ))}
          </div>

          <form onSubmit={handleSendMessage} className="p-3 bg-slate-900 border-t border-slate-800 flex gap-2">
            <input type="text" placeholder="Posez une question à l'IA..." value={inputMessage} onChange={(e) => setInputMessage(e.target.value)} className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" />
            <button type="submit" className="bg-blue-600 hover:bg-blue-500 text-white p-2.5 rounded-xl"><Send className="w-4 h-4" /></button>
          </form>
        </div>
      )}

      <button onClick={() => setIsChatOpen(!isChatOpen)} className="fixed bottom-6 right-6 p-4 bg-blue-600 hover:bg-blue-500 text-white rounded-full shadow-lg z-50 transition-transform active:scale-95">
        {isChatOpen ? <X className="w-6 h-6" /> : <Bot className="w-6 h-6" />}
      </button>

    </div>
  );
}
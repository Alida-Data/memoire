import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  ShieldCheck,
  Bot,
  Database,
  FileText,
  BarChart3,
  X,
  Send,
  UploadCloud,
  Lock,
  AlertTriangle,
  CheckCircle2,
  LayoutGrid,
  ChevronRight,
  Circle,
  Gauge,
  RotateCcw,
  Info,
} from 'lucide-react';

const API_BASE_URL = "http://localhost:8000/api/v1";

const NAV_ITEMS = [
  { id: 'copilot', label: 'Transactions', icon: Database },
  { id: 'risk', label: 'Score de risque', icon: Gauge },
  { id: 'rag', label: 'Documents', icon: FileText },
  { id: 'alerts', label: 'Alertes', icon: AlertTriangle },
  { id: 'dg', label: 'Indicateurs', icon: BarChart3 },
];

const TX_TYPES = ['TRANSFER', 'CASH_OUT', 'PAYMENT', 'CASH_IN', 'DEBIT'];

const ROLES = [
  { id: 'analyst', label: 'Analyste' },
  { id: 'dg', label: 'Direction générale' },
  { id: 'admin', label: 'Administrateur' },
];

// Simulation heuristique locale — pas un modèle entraîné.
// Chaque règle reproduit un signal classique de fraude (comptes vidés,
// compte destinataire "mule", incohérence de soldes, etc.) et retourne
// une contribution positive (pousse vers "frauduleuse") ou négative
// (pousse vers "légitime"), comme une décomposition de type SHAP.
function computeRiskScore({ txType, amount, oldBalanceOrig, newBalanceOrig, oldBalanceDest, newBalanceDest, hour, isFlagged }) {
  const amt = Number(amount) || 0;
  const oBO = Number(oldBalanceOrig) || 0;
  const nBO = Number(newBalanceOrig) || 0;
  const oBD = Number(oldBalanceDest) || 0;
  const nBD = Number(newBalanceDest) || 0;
  const h = Number(hour) || 0;
  const flagged = Number(isFlagged) === 1;

  const ratio = oBO > 0 ? amt / oBO : (amt > 0 ? 1 : 0);
  const expectedNewBO = oBO - amt;
  const mismatch = Math.abs(expectedNewBO - nBO) > Math.max(1, amt * 0.01);
  const destEmpty = oBD === 0 && nBD === 0 && amt > 0;
  const riskyType = txType === 'TRANSFER' || txType === 'CASH_OUT';
  const nightHour = h <= 5;

  const contributions = [
    { name: 'ratio_montant_solde', display: `${ratio.toFixed(2)} = ratio_montant_solde`, value: ratio > 0.85 ? 0.85 : ratio > 0.5 ? 0.35 : -0.25 },
    { name: 'oldbalanceDest', display: `${oBD} = oldbalanceDest`, value: destEmpty ? 0.9 : -0.2 },
    { name: 'newbalanceOrig', display: `${nBO} = newbalanceOrig`, value: mismatch ? 0.5 : -0.4 },
    { name: 'type', display: `${txType} = type`, value: riskyType ? 0.3 : -0.5 },
    { name: 'hour', display: `${h} = hour`, value: nightHour ? 0.25 : -0.1 },
    { name: 'montant', display: `${amt} = montant`, value: amt > 200000 ? 0.3 : -0.1 },
    { name: 'isFlaggedFraud', display: `${flagged ? 1 : 0} = isFlaggedFraud`, value: flagged ? 2.0 : -0.1 },
  ].sort((a, b) => Math.abs(b.value) - Math.abs(a.value));

  const intercept = -1.6;
  const z = intercept + contributions.reduce((s, c) => s + c.value, 0);
  const probability = 1 / (1 + Math.exp(-z));
  const decision = probability >= 0.5 ? 'FRAUDULEUSE' : 'LÉGITIME';
  const level = probability >= 0.66 ? 'ÉLEVÉ' : probability >= 0.33 ? 'MOYEN' : 'FAIBLE';

  return { probability, decision, level, contributions, z };
}

function StatCard({ label, value, sub, tone = 'neutral' }) {
  const toneColor =
    tone === 'danger' ? 'var(--danger)' : tone === 'success' ? 'var(--success)' : 'var(--accent)';
  return (
    <div className="stat-card">
      <div className="stat-card-bar" style={{ background: toneColor }} />
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {sub && <p className="stat-sub">{sub}</p>}
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState('copilot');
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [userRole, setUserRole] = useState('analyst');

  const [fileToUpload, setFileToUpload] = useState(null);
  const [uploadStatus, setUploadStatus] = useState('');

  const [sqlPrompt, setSqlPrompt] = useState('');
  const [sqlResult, setSqlResult] = useState(null);
  const [sqlLoading, setSqlLoading] = useState(false);

  const [txType, setTxType] = useState('TRANSFER');
  const [amount, setAmount] = useState(180000);
  const [oldBalanceOrig, setOldBalanceOrig] = useState(180000);
  const [newBalanceOrig, setNewBalanceOrig] = useState(0);
  const [oldBalanceDest, setOldBalanceDest] = useState(0);
  const [newBalanceDest, setNewBalanceDest] = useState(0);
  const [hour, setHour] = useState(3);
  const [isFlagged, setIsFlagged] = useState(0);

  const riskResult = useMemo(() => computeRiskScore({
    txType, amount, oldBalanceOrig, newBalanceOrig, oldBalanceDest, newBalanceDest, hour, isFlagged
  }), [txType, amount, oldBalanceOrig, newBalanceOrig, oldBalanceDest, newBalanceDest, hour, isFlagged]);

  // Statistiques du tableau de bord — évoluent à chaque transaction analysée,
  // plutôt que d'être figées.
  // Aucune valeur inventée ici : null tant que rien n'a été confirmé par
  // la base de données réelle.
  const [analyzedCount, setAnalyzedCount] = useState(null);
  const [openAlerts, setOpenAlerts] = useState(null);
  const [amountAtRisk, setAmountAtRisk] = useState(null);
  const [lastLogged, setLastLogged] = useState(null);
  // 'loading' → en attente de l'API · 'api' → vraies données reçues ·
  // 'error' → l'API n'a pas répondu, aucune donnée à afficher.
  const [statsSource, setStatsSource] = useState('loading');
  const [statsLoading, setStatsLoading] = useState(true);

  // Résultat renvoyé par le vrai modèle (endpoint FastAPI qui charge le
  // modèle XGBoost depuis le registre MLflow). null tant qu'aucune analyse
  // n'a été lancée.
  const [apiResult, setApiResult] = useState(null);
  const [apiLoading, setApiLoading] = useState(false);
  const [apiError, setApiError] = useState(null);

  const formatAmountM = (n) =>
    (n / 1000000).toLocaleString('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' M';

  const handleAnalyzeTransaction = async () => {
    setApiLoading(true);
    setApiError(null);

    // Adaptez ces clés au schéma réellement attendu par votre endpoint
    // FastAPI (les mêmes colonnes que celles utilisées à l'entraînement,
    // avant le pd.get_dummies fait côté serveur).
    const payload = {
      type: txType,
      amount: Number(amount) || 0,
      oldbalanceOrg: Number(oldBalanceOrig) || 0,
      newbalanceOrig: Number(newBalanceOrig) || 0,
      oldbalanceDest: Number(oldBalanceDest) || 0,
      newbalanceDest: Number(newBalanceDest) || 0,
      hour: Number(hour) || 0,
      isFlaggedFraud: Number(isFlagged) || 0,
      user_role: userRole,
    };

    let decision, probability, source;

    try {
      const res = await fetch(`${API_BASE_URL}/predict-fraud`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      // Tolère plusieurs formats de réponse possibles côté FastAPI.
      const rawProb = data.probability ?? data.fraud_probability ?? data.score ?? null;
      const rawDecision = data.decision ?? (
        (data.prediction === 1 || data.is_fraud === true) ? 'FRAUDULEUSE' : 'LÉGITIME'
      );
      if (rawProb === null) throw new Error("Réponse inattendue de l'API");

      probability = Number(rawProb);
      decision = rawDecision;
      source = 'api';
      setApiResult({ decision, probability, source });
    } catch (err) {
      // Le modèle n'est pas encore joignable (endpoint absent, backend
      // arrêté...) — on retombe sur l'estimation locale plutôt que de
      // bloquer l'utilisateur, mais on le signale clairement.
      setApiError(err.message || 'API indisponible');
      decision = riskResult.decision;
      probability = riskResult.probability;
      source = 'local';
      setApiResult({ decision, probability, source });
    } finally {
      setApiLoading(false);
    }

    // On ne fait évoluer les compteurs du tableau de bord que s'ils
    // reposent sur de vraies données PostgreSQL — jamais sur un chiffre
    // inventé, et jamais sur `null`.
    if (statsSource === 'api') {
      setAnalyzedCount(c => (c ?? 0) + 1);
      if (decision === 'FRAUDULEUSE') {
        setOpenAlerts(a => (a ?? 0) + 1);
        setAmountAtRisk(a => (a ?? 0) + (Number(amount) || 0));
      }
    }
    setLastLogged({ decision, score: probability, source, ts: new Date(), dashboardUpdated: statsSource === 'api' });
  };

  const [messages, setMessages] = useState([
    { role: 'assistant', text: "Bonjour. Je suis relié à l'infrastructure de données. Posez-moi une question sur les transactions ou les documents indexés." }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const scrollRef = useRef(null);

  useEffect(() => {
    fetch("http://localhost:8000/")
      .then(res => res.json())
      .then(data => console.log("Connexion API établie :", data))
      .catch(() => console.log("API non disponible actuellement"));
  }, []);

  // Charge les vraies statistiques (comptages PostgreSQL) au démarrage.
  // Adaptez l'URL/le format de réponse à votre route FastAPI réelle.
  useEffect(() => {
    let cancelled = false;
    setStatsLoading(true);
    fetch(`${API_BASE_URL}/dashboard-stats`)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(data => {
        if (cancelled) return;
        const analyzed = data.analyzed_count ?? data.transactions_analyzed ?? null;
        const alerts = data.open_alerts ?? data.alerts_count ?? null;
        const atRisk = data.amount_at_risk ?? data.amount_flagged ?? null;
        if (analyzed === null || alerts === null || atRisk === null) {
          throw new Error("Réponse inattendue de l'API");
        }
        setAnalyzedCount(Number(analyzed));
        setOpenAlerts(Number(alerts));
        setAmountAtRisk(Number(atRisk));
        setStatsSource('api');
      })
      .catch(() => {
        if (cancelled) return;
        // Le backend ne fournit pas encore cette route : on n'invente pas
        // de chiffres de remplacement, on affiche l'absence de données.
        setAnalyzedCount(null);
        setOpenAlerts(null);
        setAmountAtRisk(null);
        setStatsSource('error');
      })
      .finally(() => {
        if (!cancelled) setStatsLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isChatOpen]);

  const handleUpload = async () => {
    if (!fileToUpload) return;
    setUploadStatus('Envoi vers le stockage et indexation en cours…');

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
        setUploadStatus(`Document indexé : ${data.gcs_uri}`);
      } else {
        setUploadStatus(`Échec de l'envoi : ${data.detail}`);
      }
    } catch (err) {
      setUploadStatus("Le serveur n'a pas répondu. Vérifiez la connexion à l'API.");
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

      let responseText = data.response;
      if (typeof responseText === 'object') {
        responseText = JSON.stringify(responseText, null, 2);
      }

      setMessages(prev => [...prev, { role: 'assistant', text: responseText }]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', text: "Le serveur n'a pas répondu. Réessayez dans un instant." }]);
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
      setSqlResult({ type: 'error', message: "Le serveur de requêtes n'a pas répondu." });
    } finally {
      setSqlLoading(false);
    }
  };

  const currentNav = NAV_ITEMS.find(n => n.id === activeTab);

  return (
    <div className="platform">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

        .platform {
          --bg: #eef1f5;
          --panel: #ffffff;
          --panel-2: #f5f7fa;
          --border: #e1e5eb;
          --border-soft: #eceef2;
          --text: #1c2430;
          --text-muted: #667085;
          --text-faint: #98a2b3;
          --accent: #2e6b93;
          --accent-dim: #7fa9c4;
          --on-accent: #ffffff;
          --danger: #d6453d;
          --danger-dim: #fbe4e2;
          --success: #2f9e6e;
          --success-dim: #e1f5ea;
          --shadow: 0 1px 2px rgba(16,24,40,0.04), 0 4px 10px rgba(16,24,40,0.05);

          --sb-bg-1: #081617;
          --sb-bg-2: #0c3a3b;
          --sb-bg-3: #12ab8d;
          --sb-text: #f0f9f7;
          --sb-text-muted: #a9d2c9;
          --sb-text-faint: #6f9c95;
          --sb-surface: rgba(255,255,255,0.07);
          --sb-border: rgba(255,255,255,0.13);
          --sb-accent: #5be8c9;
          font-family: 'IBM Plex Sans', sans-serif;
          background: var(--bg);
          color: var(--text);
          min-height: 100vh;
          display: flex;
        }
        .platform .mono { font-family: 'IBM Plex Mono', monospace; }
        .platform .display { font-family: 'Fraunces', serif; }

        /* Sidebar */
        .sidebar {
          width: 236px;
          flex-shrink: 0;
          background: linear-gradient(150deg, var(--sb-bg-1) 0%, var(--sb-bg-2) 48%, var(--sb-bg-3) 100%);
          border-right: 1px solid var(--border);
          display: flex;
          flex-direction: column;
          padding: 22px 16px;
          position: sticky;
          top: 0;
          height: 100vh;
        }
        .brand {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 4px 6px 22px 6px;
          border-bottom: 1px solid var(--sb-border);
          margin-bottom: 18px;
        }
        .brand-mark {
          width: 34px;
          height: 34px;
          border-radius: 4px;
          background: var(--sb-surface);
          border: 1px solid var(--sb-border);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--sb-accent);
          flex-shrink: 0;
        }
        .brand-name {
          font-family: 'Fraunces', serif;
          font-size: 15.5px;
          font-weight: 500;
          line-height: 1.2;
          color: var(--sb-text);
        }
        .brand-sub {
          font-size: 10.5px;
          color: var(--sb-text-faint);
          margin-top: 2px;
        }
        .nav-list {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .nav-item {
          display: flex;
          align-items: center;
          gap: 11px;
          padding: 9px 10px;
          border-radius: 4px;
          font-size: 13.5px;
          color: var(--sb-text-muted);
          cursor: pointer;
          border: 1px solid transparent;
          transition: background 0.15s, color 0.15s;
          background: none;
          text-align: left;
          width: 100%;
        }
        .nav-item:hover {
          background: var(--sb-surface);
          color: var(--sb-text);
        }
        .nav-item.active {
          background: var(--sb-surface);
          color: var(--sb-text);
          border-color: var(--sb-border);
          position: relative;
        }
        .nav-item.active::before {
          content: '';
          position: absolute;
          left: -16px;
          top: 8px;
          bottom: 8px;
          width: 2px;
          background: var(--sb-accent);
        }
        .nav-item svg { flex-shrink: 0; }

        .sidebar-footer {
          margin-top: auto;
          padding-top: 16px;
          border-top: 1px solid var(--sb-border);
        }
        .role-box {
          background: var(--sb-surface);
          border: 1px solid var(--sb-border);
          border-radius: 4px;
          padding: 10px 11px;
        }
        .role-box-label {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 10.5px;
          color: var(--sb-text-faint);
          margin-bottom: 6px;
        }
        .role-select {
          width: 100%;
          background: transparent;
          border: none;
          color: var(--sb-text);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
        }
        .role-select option { background: var(--sb-bg-2); color: var(--sb-text); }
        .role-display {
          font-size: 13px;
          font-weight: 500;
          color: var(--sb-text);
        }

        /* Main */
        .main-col {
          flex: 1;
          min-width: 0;
          display: flex;
          flex-direction: column;
        }
        .topbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 20px 32px;
          border-bottom: 1px solid var(--border-soft);
        }
        .topbar-title {
          font-family: 'Fraunces', serif;
          font-size: 21px;
          font-weight: 500;
        }
        .topbar-status {
          display: flex;
          align-items: center;
          gap: 7px;
          font-size: 12px;
          color: var(--text-muted);
          margin-top: 3px;
        }
        .status-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: var(--success);
        }
        .assistant-toggle {
          display: flex;
          align-items: center;
          gap: 8px;
          background: var(--panel-2);
          border: 1px solid var(--border);
          color: var(--text);
          padding: 9px 14px;
          border-radius: 4px;
          font-size: 13px;
          cursor: pointer;
          transition: border-color 0.15s;
        }
        .assistant-toggle:hover { border-color: var(--accent-dim); }

        .content {
          flex: 1;
          padding: 28px 32px 40px 32px;
          max-width: 1080px;
        }

        .section-head { margin-bottom: 22px; }
        .section-title {
          font-size: 18px;
          font-weight: 600;
          margin-bottom: 5px;
        }
        .section-desc {
          font-size: 13px;
          color: var(--text-muted);
          max-width: 560px;
          line-height: 1.5;
        }

        /* Stat cards */
        .stat-row {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1px;
          background: var(--border);
          border: 1px solid var(--border);
          margin-bottom: 26px;
          box-shadow: var(--shadow);
          border-radius: 6px;
          overflow: hidden;
        }
        .stat-card {
          background: var(--panel);
          padding: 16px 18px;
          position: relative;
        }
        .stat-card-bar {
          position: absolute;
          top: 0; left: 0;
          width: 100%;
          height: 2px;
        }
        .stat-label { font-size: 11.5px; color: var(--text-faint); margin-bottom: 8px; }
        .stat-value { font-family: 'IBM Plex Mono', monospace; font-size: 22px; font-weight: 500; }
        .stat-sub { font-size: 11.5px; color: var(--text-muted); margin-top: 4px; }
        .stats-source-note {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 11px;
          color: var(--text-faint);
          margin: -16px 0 22px 2px;
        }
        .stats-source-note.api { color: var(--success); }
        .stats-source-note.error { color: #9a6a12; }

        /* Query form */
        .query-form { display: flex; gap: 10px; margin-bottom: 22px; }
        .query-input {
          flex: 1;
          background: var(--panel);
          border: 1px solid var(--border);
          border-radius: 4px;
          padding: 12px 14px;
          font-size: 13.5px;
          color: var(--text);
        }
        .query-input:focus { outline: none; border-color: var(--accent-dim); }
        .query-input::placeholder { color: var(--text-faint); }
        .btn-primary {
          background: var(--accent);
          color: var(--on-accent);
          border: none;
          padding: 12px 22px;
          border-radius: 4px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          transition: opacity 0.15s;
          white-space: nowrap;
        }
        .btn-primary:hover { opacity: 0.88; }
        .btn-primary:disabled { opacity: 0.5; cursor: default; }

        /* Ledger table */
        .ledger {
          border: 1px solid var(--border);
          background: var(--panel);
          border-radius: 6px;
          box-shadow: var(--shadow);
          overflow: hidden;
        }
        .ledger-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 11px 16px;
          border-bottom: 1px solid var(--border);
          font-size: 11.5px;
          color: var(--text-muted);
        }
        .ledger-ok { color: var(--success); display: flex; align-items: center; gap: 5px; }
        table.data-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
        table.data-table thead th {
          text-align: left;
          padding: 10px 16px;
          font-size: 10.5px;
          color: var(--text-faint);
          font-weight: 500;
          border-bottom: 1px solid var(--border-soft);
        }
        table.data-table tbody td {
          padding: 10px 16px;
          border-bottom: 1px solid var(--border-soft);
          font-family: 'IBM Plex Mono', monospace;
          color: var(--text);
        }
        table.data-table tbody tr:last-child td { border-bottom: none; }
        table.data-table tbody tr:hover { background: var(--panel-2); }
        .error-banner {
          background: var(--danger-dim);
          border: 1px solid var(--danger);
          color: #9c2f28;
          padding: 12px 16px;
          border-radius: 4px;
          font-size: 13px;
        }

        /* Risk simulator */
        .risk-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 18px;
          align-items: start;
        }
        .risk-panel {
          background: var(--panel);
          border: 1px solid var(--border);
          border-radius: 6px;
          box-shadow: var(--shadow);
          padding: 20px;
        }
        .risk-panel-title {
          font-size: 13.5px;
          font-weight: 600;
          margin-bottom: 16px;
          padding-bottom: 12px;
          border-bottom: 1px solid var(--border-soft);
        }
        .field-group { margin-bottom: 16px; }
        .field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .field-label {
          display: block;
          font-size: 11.5px;
          color: var(--text-muted);
          margin-bottom: 6px;
        }
        .field-input, .field-select {
          width: 100%;
          background: var(--panel);
          border: 1px solid var(--border);
          border-radius: 4px;
          padding: 9px 11px;
          font-size: 13px;
          color: var(--text);
        }
        .field-input:focus, .field-select:focus { outline: none; border-color: var(--accent-dim); }
        .slider-row { display: flex; align-items: center; gap: 10px; }
        .slider { flex: 1; accent-color: var(--accent); }
        .slider-value {
          font-size: 12.5px;
          color: var(--text);
          min-width: 20px;
          text-align: center;
        }
        .icon-btn {
          background: var(--panel-2);
          border: 1px solid var(--border);
          color: var(--text-muted);
          border-radius: 4px;
          padding: 6px;
          cursor: pointer;
          display: flex;
          align-items: center;
        }
        .icon-btn:hover { color: var(--text); }
        .radio-group { display: flex; gap: 8px; }
        .radio-pill {
          display: flex;
          align-items: center;
          gap: 6px;
          border: 1px solid var(--border);
          background: var(--panel);
          padding: 7px 16px;
          border-radius: 999px;
          font-size: 12.5px;
          color: var(--text-muted);
          cursor: pointer;
        }
        .radio-pill.checked {
          border-color: var(--accent);
          color: var(--accent);
          background: color-mix(in srgb, var(--accent) 8%, var(--panel));
        }
        .radio-pill input { accent-color: var(--accent); }

        .btn-analyze {
          width: 100%;
          background: var(--accent);
          color: var(--on-accent);
          border: none;
          padding: 13px 18px;
          border-radius: 4px;
          font-size: 13.5px;
          font-weight: 600;
          cursor: pointer;
          margin-top: 4px;
          transition: opacity 0.15s;
        }
        .btn-analyze:hover { opacity: 0.9; }
        .analyze-note {
          font-size: 11.5px;
          color: var(--text-muted);
          margin-top: 10px;
          line-height: 1.5;
        }

        .decision-badge {
          display: inline-block;
          padding: 9px 16px;
          border-radius: 4px;
          font-size: 13.5px;
          font-weight: 600;
          letter-spacing: 0.02em;
        }
        .decision-badge.success { background: var(--success-dim); color: #1f6b48; border: 1px solid var(--success); }
        .decision-badge.danger { background: var(--danger-dim); color: #9c2f28; border: 1px solid var(--danger); }
        .decision-badge.subtle { opacity: 0.8; font-weight: 500; }

        .api-warning {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          background: #fbf0dc;
          border: 1px solid #e8c778;
          color: #7a5a10;
          padding: 10px 12px;
          border-radius: 4px;
          font-size: 11.5px;
          line-height: 1.5;
          margin-bottom: 16px;
        }
        .api-warning code { background: rgba(0,0,0,0.06); padding: 1px 4px; border-radius: 3px; }

        .local-preview-head {
          font-size: 10.5px;
          text-transform: none;
          color: var(--text-faint);
          letter-spacing: 0.02em;
          margin: 4px 0 14px 0;
          padding-top: 12px;
          border-top: 1px dashed var(--border-soft);
        }

        .btn-analyze:disabled { opacity: 0.6; cursor: default; }

        .score-value { font-size: 26px; font-weight: 500; color: var(--text); }

        .level-badge {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          padding: 7px 14px;
          border-radius: 999px;
          font-size: 12.5px;
          font-weight: 600;
        }
        .level-badge.success { background: var(--success-dim); color: #1f6b48; }
        .level-badge.warn { background: #fbf0dc; color: #9a6a12; }
        .level-badge.danger { background: var(--danger-dim); color: #9c2f28; }

        .waterfall-head {
          display: flex;
          align-items: center;
          gap: 7px;
          font-size: 11.5px;
          color: var(--text-muted);
          margin: 18px 0 12px 0;
          padding-top: 14px;
          border-top: 1px solid var(--border-soft);
        }
        .waterfall-row {
          display: grid;
          grid-template-columns: 140px 1fr;
          align-items: center;
          gap: 10px;
          margin-bottom: 9px;
        }
        .waterfall-label {
          font-size: 10.5px;
          color: var(--text-muted);
          text-align: right;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .waterfall-track {
          position: relative;
          height: 22px;
          background: var(--panel-2);
          border-radius: 3px;
        }
        .waterfall-mid {
          position: absolute;
          left: 50%;
          top: 0;
          bottom: 0;
          width: 1px;
          background: var(--border);
        }
        .waterfall-bar {
          position: absolute;
          top: 2px;
          bottom: 2px;
          border-radius: 3px;
          display: flex;
          align-items: center;
          justify-content: center;
          min-width: 2px;
        }
        .waterfall-bar.pos { background: var(--danger); }
        .waterfall-bar.neg { background: var(--accent); }
        .waterfall-val {
          font-size: 10px;
          color: var(--on-accent);
          font-weight: 600;
          white-space: nowrap;
          padding: 0 4px;
        }

        .disclaimer-banner {
          display: flex;
          align-items: flex-start;
          gap: 9px;
          margin-top: 18px;
          padding: 12px 16px;
          background: #fbf0dc;
          border: 1px solid #e8c778;
          color: #7a5a10;
          border-radius: 6px;
          font-size: 12.5px;
          line-height: 1.5;
        }

        /* Upload */
        .dropzone {
          border: 1px dashed var(--border);
          background: var(--panel);
          padding: 40px 30px;
          text-align: center;
          border-radius: 6px;
        }
        .dropzone-icon {
          width: 44px; height: 44px;
          border: 1px solid var(--border);
          background: var(--panel-2);
          border-radius: 4px;
          display: flex; align-items: center; justify-content: center;
          margin: 0 auto 16px auto;
          color: var(--accent);
        }
        .file-input {
          font-size: 12.5px;
          color: var(--text-muted);
        }
        .file-input::file-selector-button {
          background: var(--panel-2);
          border: 1px solid var(--border);
          color: var(--text);
          padding: 7px 13px;
          border-radius: 4px;
          margin-right: 12px;
          font-size: 12px;
          cursor: pointer;
        }
        .upload-status {
          margin-top: 14px;
          font-family: 'IBM Plex Mono', monospace;
          font-size: 11.5px;
          color: var(--accent);
        }

        .placeholder-block {
          border: 1px solid var(--border-soft);
          background: var(--panel);
          padding: 60px 30px;
          text-align: center;
          border-radius: 6px;
          box-shadow: var(--shadow);
        }

        /* Chat dock */
        .chat-dock {
          width: 340px;
          flex-shrink: 0;
          background: var(--panel);
          border-left: 1px solid var(--border);
          display: flex;
          flex-direction: column;
          height: 100vh;
          position: sticky;
          top: 0;
        }
        .chat-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 18px 18px 16px 18px;
          border-bottom: 1px solid var(--border-soft);
        }
        .chat-head-title { display: flex; align-items: center; gap: 10px; }
        .chat-avatar {
          width: 30px; height: 30px;
          border-radius: 4px;
          background: var(--panel-2);
          border: 1px solid var(--accent-dim);
          display: flex; align-items: center; justify-content: center;
          color: var(--accent);
        }
        .chat-title-text { font-size: 13.5px; font-weight: 600; }
        .chat-status { font-size: 10.5px; color: var(--success); display: flex; align-items: center; gap: 5px; margin-top: 2px; }
        .chat-close { background: none; border: none; color: var(--text-faint); cursor: pointer; padding: 4px; }
        .chat-close:hover { color: var(--text); }
        .chat-body { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
        .msg-row { display: flex; }
        .msg-row.user { justify-content: flex-end; }
        .msg-bubble {
          max-width: 86%;
          padding: 10px 13px;
          border-radius: 4px;
          font-size: 12.5px;
          line-height: 1.5;
        }
        .msg-bubble.assistant { background: var(--panel-2); border: 1px solid var(--border-soft); color: var(--text); }
        .msg-bubble.user { background: var(--accent); color: var(--on-accent); font-weight: 500; }
        .chat-form { display: flex; gap: 8px; padding: 14px; border-top: 1px solid var(--border-soft); }
        .chat-input {
          flex: 1;
          background: var(--bg);
          border: 1px solid var(--border);
          border-radius: 4px;
          padding: 9px 12px;
          font-size: 12.5px;
          color: var(--text);
        }
        .chat-input:focus { outline: none; border-color: var(--accent-dim); }
        .chat-send {
          background: var(--accent);
          border: none;
          color: var(--on-accent);
          border-radius: 4px;
          width: 36px;
          display: flex; align-items: center; justify-content: center;
          cursor: pointer;
        }
      `}</style>

      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><ShieldCheck size={18} /></div>
          <div>
            <div className="brand-name">Vigie</div>
            <div className="brand-sub">Détection de fraude</div>
          </div>
        </div>

        <nav className="nav-list">
          {NAV_ITEMS.map(item => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
              >
                <Icon size={16} />
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="role-box">
            <div className="role-box-label"><Lock size={11} /> Rôle actif</div>
            <div className="role-display">
              {ROLES.find(r => r.id === userRole)?.label || userRole}
            </div>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="main-col">
        <header className="topbar">
          <div>
            <div className="topbar-title">{currentNav?.label}</div>
            <div className="topbar-status">
              <span className="status-dot" /> Cloud SQL PostgreSQL &amp; stockage documentaire — connecté
            </div>
          </div>
          <button className="assistant-toggle" onClick={() => setIsChatOpen(!isChatOpen)}>
            <Bot size={15} />
            {isChatOpen ? 'Masquer l\'assistant' : 'Ouvrir l\'assistant'}
          </button>
        </header>

        <div className="content">
          {activeTab === 'copilot' && (
            <div>
              <div className="stat-row">
                <StatCard
                  label="Transactions analysées (24 h)"
                  value={statsLoading ? '…' : analyzedCount !== null ? analyzedCount.toLocaleString('fr-FR') : '—'}
                  tone="neutral"
                />
                <StatCard
                  label="Signalements ouverts"
                  value={statsLoading ? '…' : openAlerts !== null ? String(openAlerts) : '—'}
                  sub="À traiter"
                  tone="danger"
                />
                <StatCard
                  label="Montant sous surveillance"
                  value={statsLoading ? '…' : amountAtRisk !== null ? formatAmountM(amountAtRisk) : '—'}
                  sub="XOF"
                  tone="success"
                />
              </div>
              <div className={`stats-source-note ${statsSource}`}>
                {statsLoading
                  ? 'Chargement des statistiques depuis la base…'
                  : statsSource === 'api'
                    ? <><CheckCircle2 size={12} /> Données chargées depuis PostgreSQL</>
                    : <><AlertTriangle size={12} /> Données indisponibles — <code className="mono">GET {API_BASE_URL}/dashboard-stats</code> ne répond pas. Aucun chiffre inventé n'est affiché.</>
                }
              </div>

              <div className="section-head">
                <div className="section-title">Interroger les transactions</div>
                <div className="section-desc">Posez une question en langage naturel ; elle est traduite en requête sur la base PostgreSQL.</div>
              </div>

              <form onSubmit={handleSqlSubmit} className="query-form">
                <input
                  type="text"
                  placeholder="Ex. : montre les transactions suspectes des dernières 24 heures"
                  value={sqlPrompt}
                  onChange={(e) => setSqlPrompt(e.target.value)}
                  className="query-input"
                />
                <button type="submit" disabled={sqlLoading} className="btn-primary">
                  {sqlLoading ? 'Analyse…' : 'Exécuter'}
                </button>
              </form>

              {sqlResult && (
                sqlResult.type === 'error' ? (
                  <div className="error-banner">{sqlResult.message}</div>
                ) : (
                  <div className="ledger">
                    <div className="ledger-head">
                      <span>{sqlResult.data?.length || 0} ligne(s) retournée(s)</span>
                      <span className="ledger-ok"><CheckCircle2 size={13} /> Requête exécutée</span>
                    </div>
                    <div style={{ overflowX: 'auto', maxHeight: 380 }}>
                      <table className="data-table">
                        <thead>
                          <tr>
                            {sqlResult.columns?.map((col, i) => <th key={i}>{col}</th>)}
                          </tr>
                        </thead>
                        <tbody>
                          {sqlResult.data?.length > 0 ? (
                            sqlResult.data.map((row, ri) => (
                              <tr key={ri}>
                                {row.map((cell, ci) => <td key={ci}>{String(cell)}</td>)}
                              </tr>
                            ))
                          ) : (
                            <tr><td colSpan={sqlResult.columns?.length || 1} style={{ textAlign: 'center', color: 'var(--text-faint)', fontFamily: 'IBM Plex Sans' }}>Aucun résultat.</td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )
              )}
            </div>
          )}

          {activeTab === 'risk' && (
            <div>
              <div className="section-head">
                <div className="section-title">Simulateur de score de risque</div>
                <div className="section-desc">Renseignez les caractéristiques d'une transaction : le score se recalcule automatiquement à chaque modification.</div>
              </div>

              <div className="risk-grid">
                {/* Paramètres */}
                <div className="risk-panel">
                  <div className="risk-panel-title">Paramètres de la transaction</div>

                  <div className="field-group">
                    <label className="field-label">Type de transaction</label>
                    <select className="field-select" value={txType} onChange={(e) => setTxType(e.target.value)}>
                      {TX_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>

                  <div className="field-row">
                    <div className="field-group">
                      <label className="field-label">Montant</label>
                      <input type="number" className="field-input" value={amount} onChange={(e) => setAmount(e.target.value)} />
                    </div>
                    <div className="field-group">
                      <label className="field-label">Solde initial expéditeur</label>
                      <input type="number" className="field-input" value={oldBalanceOrig} onChange={(e) => setOldBalanceOrig(e.target.value)} />
                    </div>
                  </div>

                  <div className="field-row">
                    <div className="field-group">
                      <label className="field-label">Nouveau solde expéditeur</label>
                      <input type="number" className="field-input" value={newBalanceOrig} onChange={(e) => setNewBalanceOrig(e.target.value)} />
                    </div>
                    <div className="field-group">
                      <label className="field-label">Solde initial destinataire</label>
                      <input type="number" className="field-input" value={oldBalanceDest} onChange={(e) => setOldBalanceDest(e.target.value)} />
                    </div>
                  </div>

                  <div className="field-group">
                    <label className="field-label">Nouveau solde destinataire</label>
                    <input type="number" className="field-input" value={newBalanceDest} onChange={(e) => setNewBalanceDest(e.target.value)} />
                  </div>

                  <div className="field-group">
                    <label className="field-label">Heure de la journée (0h–23h)</label>
                    <div className="slider-row">
                      <input type="range" min="0" max="23" value={hour} onChange={(e) => setHour(e.target.value)} className="slider" />
                      <span className="slider-value mono">{hour}</span>
                      <button type="button" className="icon-btn" onClick={() => setHour(3)} title="Réinitialiser"><RotateCcw size={13} /></button>
                    </div>
                  </div>

                  <div className="field-group">
                    <label className="field-label">Alerte système automatique (isFlaggedFraud)</label>
                    <div className="radio-group">
                      <label className={`radio-pill ${Number(isFlagged) === 0 ? 'checked' : ''}`}>
                        <input type="radio" name="flagged" checked={Number(isFlagged) === 0} onChange={() => setIsFlagged(0)} /> 0
                      </label>
                      <label className={`radio-pill ${Number(isFlagged) === 1 ? 'checked' : ''}`}>
                        <input type="radio" name="flagged" checked={Number(isFlagged) === 1} onChange={() => setIsFlagged(1)} /> 1
                      </label>
                    </div>
                  </div>

                  <button type="button" className="btn-analyze" onClick={handleAnalyzeTransaction} disabled={apiLoading}>
                    {apiLoading ? 'Analyse en cours…' : 'Analyser la transaction'}
                  </button>
                  {lastLogged && (
                    <p className="analyze-note">
                      Dernière transaction : <strong>{lastLogged.decision}</strong> ({(lastLogged.score * 100).toFixed(2)}%, {lastLogged.source === 'api' ? 'modèle réel' : 'simulation locale'}) — {lastLogged.dashboardUpdated ? 'cartes du tableau de bord mises à jour.' : "tableau de bord non mis à jour (pas encore connecté à PostgreSQL)."}
                    </p>
                  )}
                </div>

                {/* Résultat */}
                <div className="risk-panel">
                  <div className="risk-panel-title">Résultat du modèle</div>

                  {apiResult && apiResult.source === 'api' && (
                    <>
                      <div className="field-group">
                        <label className="field-label">Décision du modèle (XGBoost — MLflow)</label>
                        <div className={`decision-badge ${apiResult.decision === 'FRAUDULEUSE' ? 'danger' : 'success'}`}>
                          {apiResult.decision}
                        </div>
                      </div>
                      <div className="field-group">
                        <label className="field-label">Score de risque (probabilité de fraude)</label>
                        <div className="score-value mono">{(apiResult.probability * 100).toFixed(2)}%</div>
                      </div>
                    </>
                  )}

                  {apiError && (
                    <div className="api-warning">
                      <AlertTriangle size={14} />
                      <span>API modèle indisponible ({apiError}) — <code className="mono">POST {API_BASE_URL}/predict-fraud</code> ne répond pas encore. Le résultat ci-dessous et les cartes du tableau de bord utilisent l'estimation locale en attendant.</span>
                    </div>
                  )}

                  <div className="local-preview-head">
                    Estimation locale (aperçu en temps réel)
                  </div>

                  <div className="field-group">
                    <label className="field-label">Décision estimée</label>
                    <div className={`decision-badge subtle ${riskResult.decision === 'FRAUDULEUSE' ? 'danger' : 'success'}`}>
                      {riskResult.decision}
                    </div>
                  </div>

                  <div className="field-group">
                    <label className="field-label">Score estimé</label>
                    <div className="score-value mono">{(riskResult.probability * 100).toFixed(2)}%</div>
                  </div>

                  <div className="field-group">
                    <label className="field-label">Niveau de risque</label>
                    <div className={`level-badge ${riskResult.level === 'ÉLEVÉ' ? 'danger' : riskResult.level === 'MOYEN' ? 'warn' : 'success'}`}>
                      <Circle size={7} fill="currentColor" stroke="none" /> {riskResult.level}
                    </div>
                  </div>

                  <div className="waterfall-head">
                    <Gauge size={13} /> Impact des variables — explication de l'estimation locale
                  </div>
                  <div className="waterfall">
                    {riskResult.contributions.map((c) => {
                      const maxAbs = Math.max(...riskResult.contributions.map(x => Math.abs(x.value)), 0.1);
                      const widthPct = (Math.abs(c.value) / maxAbs) * 50;
                      const positive = c.value >= 0;
                      return (
                        <div className="waterfall-row" key={c.name}>
                          <div className="waterfall-label mono">{c.display}</div>
                          <div className="waterfall-track">
                            <div className="waterfall-mid" />
                            <div
                              className={`waterfall-bar ${positive ? 'pos' : 'neg'}`}
                              style={{
                                width: `${widthPct}%`,
                                left: positive ? '50%' : `${50 - widthPct}%`,
                              }}
                            >
                              <span className="waterfall-val mono">{positive ? '+' : ''}{c.value.toFixed(2)}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              <div className="disclaimer-banner">
                <Info size={15} />
                <span><strong>Note :</strong> le bouton "Analyser la transaction" interroge <code className="mono">POST {API_BASE_URL}/predict-fraud</code>, censé charger votre modèle XGBoost depuis le registre MLflow. Tant que cette route n'existe pas côté backend, l'app retombe automatiquement sur une estimation locale par règles (clairement indiquée) — elle ne remplace pas le modèle entraîné.</span>
              </div>
            </div>
          )}

          {activeTab === 'rag' && (
            <div>
              <div className="section-head">
                <div className="section-title">Documents de référence</div>
                <div className="section-desc">Envoyez des documents non structurés (politiques, rapports, dossiers) pour enrichir les réponses de l'assistant.</div>
              </div>
              <div className="dropzone">
                <div className="dropzone-icon"><UploadCloud size={20} /></div>
                <input
                  type="file"
                  onChange={(e) => setFileToUpload(e.target.files[0])}
                  className="file-input"
                />
                <div style={{ marginTop: 18 }}>
                  <button onClick={handleUpload} className="btn-primary">Envoyer le document</button>
                </div>
                {uploadStatus && <p className="upload-status">{uploadStatus}</p>}
              </div>
            </div>
          )}

          {activeTab === 'alerts' && (
            <div>
              <div className="section-head">
                <div className="section-title">Alertes de fraude</div>
                <div className="section-desc">Anomalies détectées automatiquement sur la fenêtre horaire active.</div>
              </div>
              <div className="placeholder-block">
                <AlertTriangle size={28} style={{ color: 'var(--text-faint)', margin: '0 auto 12px auto' }} />
                <p style={{ fontSize: 14, fontWeight: 500, marginBottom: 4 }}>Aucune anomalie critique en attente</p>
                <p style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Le module d'alertes surveille les flux en continu.</p>
              </div>
            </div>
          )}

          {activeTab === 'dg' && (
            <div>
              <div className="section-head">
                <div className="section-title">Indicateurs décisionnels</div>
                <div className="section-desc">Tendances financières et performance du dispositif anti-fraude.</div>
              </div>
              <div className="placeholder-block">
                <BarChart3 size={28} style={{ color: 'var(--text-faint)', margin: '0 auto 12px auto' }} />
                <p style={{ fontSize: 14, fontWeight: 500, marginBottom: 4 }}>Tableau de bord en préparation</p>
                <p style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Les indicateurs clés s'afficheront ici une fois les données connectées.</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Chat dock */}
      {isChatOpen && (
        <aside className="chat-dock">
          <div className="chat-head">
            <div className="chat-head-title">
              <div className="chat-avatar"><Bot size={15} /></div>
              <div>
                <div className="chat-title-text">Assistant</div>
                <div className="chat-status"><Circle size={6} fill="currentColor" stroke="none" /> Connecté</div>
              </div>
            </div>
            <button className="chat-close" onClick={() => setIsChatOpen(false)}><X size={17} /></button>
          </div>

          <div className="chat-body" ref={scrollRef}>
            {messages.map((msg, i) => (
              <div key={i} className={`msg-row ${msg.role}`}>
                <div className={`msg-bubble ${msg.role}`}>{msg.text}</div>
              </div>
            ))}
          </div>

          <form onSubmit={handleSendMessage} className="chat-form">
            <input
              type="text"
              placeholder="Poser une question…"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              className="chat-input"
            />
            <button type="submit" className="chat-send"><Send size={15} /></button>
          </form>
        </aside>
      )}
    </div>
  );
}

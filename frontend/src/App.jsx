import React, { useState, useEffect, useRef, useMemo } from 'react';
import IndicatorsView from './IndicatorsView';
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

// FastAPI renvoie `detail` sous forme de simple texte la plupart du temps,
// mais sous forme de LISTE d'objets pour les erreurs de validation
// automatiques (422) — sans ce garde-fou, ça affichait juste
// "[object Object]" au lieu du vrai message.
function formatApiError(err, status) {
  const d = err?.detail;
  if (!d) return `HTTP ${status}`;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    return d.map(item => item.msg ? `${(item.loc || []).join('.')}: ${item.msg}` : JSON.stringify(item)).join(' ; ');
  }
  return JSON.stringify(d);
}

const NAV_ITEMS = [
  { id: 'copilot', label: 'Transactions', icon: Database },
  { id: 'risk', label: 'Score de risque', icon: Gauge },
  { id: 'rag', label: 'Documents', icon: FileText },
  { id: 'alerts', label: 'Alertes', icon: AlertTriangle },
  { id: 'dg', label: 'Indicateurs', icon: BarChart3 },
];

const MERCHANT_TYPES = ['physical', 'online', 'transport', 'medical', 'major', 'airlines', 'casual', 'booking'];
const CARD_TYPES = ['Basic Debit', 'Basic Credit', 'Gold Credit', 'Platinum Credit', 'Premium Debit'];
const DEVICES = ['Chrome', 'Firefox', 'Safari', 'Edge', 'iOS App', 'Android App', 'Magnetic Stripe'];
const CHANNELS = ['web', 'mobile', 'pos'];
const CURRENCIES = ['USD', 'EUR', 'GBP', 'AUD', 'SGD', 'MXN', 'NGN', 'RUB'];
const COUNTRIES = ['USA', 'UK', 'Australia', 'Singapore', 'Mexico', 'Nigeria', 'Russia', 'Germany'];
const CITY_SIZES = ['small', 'medium', 'large'];

const ROLES = [
  { id: 'analyst', label: 'Analyste' },
  { id: 'dg', label: 'Direction générale' },
  { id: 'admin', label: 'Administrateur' },
];

// Simulation heuristique locale — pas un modèle entraîné.
function computeRiskScore({ amount, cardPresent, device, velocityLastHour, highRiskMerchant, transactionHour, weekendTransaction, channel }) {
  const amt = Number(amount) || 0;
  const velocity = Number(velocityLastHour) || 0;
  const h = Number(transactionHour) || 0;
  const isHighRisk = Number(highRiskMerchant) === 1;
  const isWeekend = Number(weekendTransaction) === 1;
  const cardNotPresent = Number(cardPresent) !== 1;
  const nightHour = h <= 5 || h >= 22;
  const highVelocity = velocity >= 3;
  const posMagStripe = device === 'Magnetic Stripe';

  const contributions = [
    { name: 'montant', display: `${amt} = montant`, value: amt > 5000 ? 0.6 : amt > 1000 ? 0.15 : -0.2 },
    { name: 'high_risk_merchant', display: `${isHighRisk ? 1 : 0} = high_risk_merchant`, value: isHighRisk ? 0.9 : -0.3 },
    { name: 'velocity_last_hour', display: `${velocity} = velocity_last_hour`, value: highVelocity ? 0.7 : velocity >= 1 ? 0.1 : -0.2 },
    { name: 'card_present', display: `${cardPresent} = card_present`, value: cardNotPresent ? 0.35 : -0.3 },
    { name: 'transaction_hour', display: `${h} = transaction_hour`, value: nightHour ? 0.3 : -0.15 },
    { name: 'weekend_transaction', display: `${isWeekend ? 1 : 0} = weekend_transaction`, value: isWeekend ? 0.15 : -0.1 },
    { name: 'device', display: `${device} = device`, value: posMagStripe ? 0.2 : -0.1 },
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
  const [userRole, setUserRole] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loginError, setLoginError] = useState(null);
  const [loginLoading, setLoginLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoginLoading(true);
    setLoginError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: loginUsername, password: loginPassword }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(formatApiError(err, res.status) || 'Identifiants invalides');
      }
      const data = await res.json();
      setUserRole(data.role);
      setIsAuthenticated(true);
    } catch (err) {
      setLoginError(err.message || "Impossible de se connecter à l'API");
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
    setUserRole(null);
    setLoginUsername('');
    setLoginPassword('');
  };

  const [fileToUpload, setFileToUpload] = useState(null);
  const [uploadStatus, setUploadStatus] = useState('');
  const [documents, setDocuments] = useState([]);
  const [documentsError, setDocumentsError] = useState(null);
  const [removingDoc, setRemovingDoc] = useState(null);

  const fetchDocuments = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/documents`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setDocuments(data.documents || []);
      setDocumentsError(null);
    } catch (err) {
      setDocumentsError(err.message || 'API indisponible');
    }
  };

  const removeDocument = async (filename) => {
    setRemovingDoc(filename);
    try {
      const res = await fetch(`${API_BASE_URL}/documents/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(formatApiError(err, res.status));
      }
      await fetchDocuments();
    } catch (err) {
      setDocumentsError(err.message || 'API indisponible');
    } finally {
      setRemovingDoc(null);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const [sqlPrompt, setSqlPrompt] = useState('');
  const [sqlResult, setSqlResult] = useState(null);
  const [sqlLoading, setSqlLoading] = useState(false);

  const [amount, setAmount] = useState(150);
  const [merchantType, setMerchantType] = useState('physical');
  const [currency, setCurrency] = useState('USD');
  const [country, setCountry] = useState('USA');
  const [citySize, setCitySize] = useState('medium');
  const [cardType, setCardType] = useState('Basic Debit');
  const [cardPresent, setCardPresent] = useState(0);
  const [device, setDevice] = useState('Chrome');
  const [channel, setChannel] = useState('web');
  const [velocityLastHour, setVelocityLastHour] = useState(0);
  const [highRiskMerchant, setHighRiskMerchant] = useState(0);
  const [transactionHour, setTransactionHour] = useState(12);
  const [weekendTransaction, setWeekendTransaction] = useState(0);

  const riskResult = useMemo(() => computeRiskScore({
    amount, cardPresent, device, velocityLastHour, highRiskMerchant, transactionHour, weekendTransaction, channel
  }), [amount, cardPresent, device, velocityLastHour, highRiskMerchant, transactionHour, weekendTransaction, channel]);

  const [analyzedCount, setAnalyzedCount] = useState(null);
  const [openAlerts, setOpenAlerts] = useState(null);
  const [amountAtRisk, setAmountAtRisk] = useState(null);
  const [lastLogged, setLastLogged] = useState(null);
  const [statsSource, setStatsSource] = useState('loading');
  const [statsLoading, setStatsLoading] = useState(true);

  const [apiResult, setApiResult] = useState(null);
  const [apiLoading, setApiLoading] = useState(false);
  const [apiError, setApiError] = useState(null);

  const [sampleTransactions, setSampleTransactions] = useState([]);
  const [samplesLoading, setSamplesLoading] = useState(false);
  const [samplesError, setSamplesError] = useState(null);
  const [loadedTransaction, setLoadedTransaction] = useState(null);

  // Surveillance en direct SIMULÉE : rejoue des transactions historiques
  // au hasard comme si elles venaient d'arriver, les fait scorer par le
  // vrai modèle, et récupère les alertes générées automatiquement.
  const [liveMonitoring, setLiveMonitoring] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [alertsError, setAlertsError] = useState(null);
  const [liveStats, setLiveStats] = useState({ processed: 0, blocked: 0 });
  const [lastTick, setLastTick] = useState(null);

  const fetchAlerts = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/alerts?limit=20`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAlerts(data.alerts || []);
      setAlertsError(null);
    } catch (err) {
      setAlertsError(err.message || 'API indisponible');
    }
  };

  const runMonitorTick = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/live-monitor/tick?n=20`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setLastTick(data);
      setLiveStats(s => ({ processed: s.processed + data.processed, blocked: s.blocked + data.blocked }));
      await fetchAlerts();
    } catch (err) {
      setAlertsError(err.message || 'API indisponible');
      setLiveMonitoring(false);
    }
  };

  const resolveAlert = async (id) => {
    try {
      await fetch(`${API_BASE_URL}/alerts/${id}/resolve`, { method: 'POST' });
      await fetchAlerts();
    } catch (err) {
      setAlertsError(err.message || 'API indisponible');
    }
  };

  useEffect(() => {
    fetchAlerts();
  }, []);

  useEffect(() => {
    if (!liveMonitoring) return;
    runMonitorTick();
    const interval = setInterval(runMonitorTick, 4000);
    return () => clearInterval(interval);
  }, [liveMonitoring]);

  const loadSampleTransactions = async () => {
    setSamplesLoading(true);
    setSamplesError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/sample-transactions?limit=50`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSampleTransactions(data.transactions || []);
    } catch (err) {
      setSamplesError(err.message || 'API indisponible');
    } finally {
      setSamplesLoading(false);
    }
  };
const [copilotStats, setCopilotStats] = useState({
    total_alertes: 0,
    montant_a_risque: 0,
    currency: 'XOF'
  });
  const [copilotLoading, setCopilotLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE_URL}/copilot-kpis`)
      .then((res) => res.json())
      .then((data) => {
        setCopilotStats(data);
        setCopilotLoading(false);
      })
      .catch((err) => {
        console.error("Erreur lors de la récupération des KPIs Copilot :", err);
        setCopilotLoading(false);
      });
  }, []);

  const formatAmount = (amount) => {
    if (!amount) return '0';
    if (amount >= 1e9) return `${(amount / 1e9).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Mds`;
    if (amount >= 1e6) return `${(amount / 1e6).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} M`;
    return amount.toLocaleString('fr-FR');
  };
  
  // Normalise un champ censé être 0/1 : l'API peut renvoyer un booléen
  // (true/false, cas d'une colonne PostgreSQL de type boolean), un texte
  // ("0"/"1"/"true"), ou déjà un entier. Sans cette normalisation, un
  // booléen finit par être envoyé tel quel à /predict-fraud, que Pydantic
  // rejette ("Input should be a valid integer").
  const toBinary = (val) => {
    if (val === true || val === 1 || val === '1' || val === 'true') return 1;
    return 0;
  };

  const applySampleTransaction = (tx) => {
    setAmount(tx.amount);
    setMerchantType(tx.merchant_type ?? merchantType);
    setCurrency(tx.currency ?? currency);
    setCountry(tx.country ?? country);
    setCitySize(tx.city_size ?? citySize);
    setCardType(tx.card_type ?? cardType);
    setCardPresent(toBinary(tx.card_present));
    setDevice(tx.device ?? device);
    setChannel(tx.channel ?? channel);
    setVelocityLastHour(0);
    setHighRiskMerchant(toBinary(tx.high_risk_merchant));
    setTransactionHour(tx.transaction_hour ?? 12);
    setWeekendTransaction(toBinary(tx.weekend_transaction));
    setLoadedTransaction(tx);
    setApiResult(null);
    setApiError(null);
  };

  const formatAmountM = (n) =>
    (n / 1000000).toLocaleString('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' M';

  const handleAnalyzeTransaction = async () => {
    setApiLoading(true);
    setApiError(null);

    const payload = {
      amount: Number(amount) || 0,
      high_risk_merchant: Number(highRiskMerchant),
      transaction_hour: Number(transactionHour),
      weekend_transaction: Number(weekendTransaction),
      velocity_last_hour: Number(velocityLastHour) || 0,
      card_present: Number(cardPresent),
      merchant_type: merchantType,
      card_type: cardType,
      device,
      channel,
      country,
      city_size: citySize,
      currency,
    };

    let decision, probability, source;

    try {
      const res = await fetch(`${API_BASE_URL}/predict-fraud`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(formatApiError(err, res.status));
      }
      const data = await res.json();
      if (data.probability === undefined) throw new Error("Réponse inattendue de l'API");

      probability = Number(data.probability);
      decision = data.decision;
      source = 'api';
      setApiResult({ decision, probability, source });
    } catch (err) {
      setApiError(err.message || 'API indisponible');
      decision = riskResult.decision;
      probability = riskResult.probability;
      source = 'local';
      setApiResult({ decision, probability, source });
    } finally {
      setApiLoading(false);
    }

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
        await fetchDocuments();
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

        .sample-tx-block {
          background: var(--panel-2);
          border: 1px solid var(--border-soft);
          border-radius: 6px;
          padding: 12px;
          margin-bottom: 18px;
        }
        .sample-tx-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 12px;
          font-weight: 600;
          color: var(--text);
          margin-bottom: 8px;
        }
        .sample-tx-error {
          display: flex;
          align-items: flex-start;
          gap: 6px;
          font-size: 11px;
          color: #9a6a12;
          margin: 6px 0 0 0;
        }
        .sample-tx-list {
          display: flex;
          flex-direction: column;
          gap: 4px;
          max-height: 260px;
          overflow-y: auto;
        }
        .sample-tx-row {
          display: grid;
          grid-template-columns: 1.4fr 1fr 1fr 1fr;
          gap: 8px;
          background: var(--panel);
          border: 1px solid var(--border-soft);
          border-radius: 4px;
          padding: 7px 9px;
          font-size: 10.5px;
          color: var(--text-muted);
          cursor: pointer;
          text-align: left;
        }
        .sample-tx-row:hover { border-color: var(--accent-dim); }
        .sample-tx-row.active { border-color: var(--accent); background: var(--panel); }
        .sample-tx-fraud { color: var(--danger); font-weight: 600; }
        .sample-tx-ok { color: var(--success); font-weight: 600; }
        .sample-tx-loaded {
          font-size: 11px;
          color: var(--text-muted);
          margin: 10px 0 0 0;
          line-height: 1.5;
        }
        .model-field .field-label { display: flex; align-items: center; gap: 8px; }
        .model-tag {
          font-size: 9.5px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.03em;
          color: var(--accent);
          background: color-mix(in srgb, var(--accent) 10%, var(--panel));
          padding: 2px 7px;
          border-radius: 999px;
        }
        .demo-fields-note {
          font-size: 11px;
          color: var(--text-faint);
          font-style: italic;
          margin: -6px 0 16px 0;
        }
        .ground-truth-note {
          font-size: 11.5px;
          padding: 9px 12px;
          border-radius: 4px;
          margin-top: 4px;
          line-height: 1.5;
        }
        .ground-truth-note.match { background: var(--success-dim); color: #1f6b48; }
        .ground-truth-note.mismatch { background: var(--danger-dim); color: #9c2f28; }

        .monitor-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: var(--panel);
          border: 1px solid var(--border);
          border-radius: 6px;
          box-shadow: var(--shadow);
          padding: 14px 18px;
          margin-bottom: 14px;
        }
        .btn-monitor {
          display: flex;
          align-items: center;
          gap: 9px;
          background: var(--accent);
          color: var(--on-accent);
          border: none;
          padding: 10px 18px;
          border-radius: 4px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
        }
        .btn-monitor.active { background: var(--danger); }
        .monitor-dot {
          width: 8px; height: 8px;
          border-radius: 50%;
          background: rgba(255,255,255,0.6);
        }
        .monitor-dot.live { background: #fff; animation: pulse-dot 1.2s infinite; }
        @keyframes pulse-dot {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        .monitor-stats { font-size: 12.5px; color: var(--text-muted); }
        .monitor-stats-sep { margin: 0 8px; color: var(--border); }
        .monitor-stats-blocked { color: var(--danger); }

        .alert-list { display: flex; flex-direction: column; gap: 8px; margin-top: 16px; }
        .alert-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: var(--panel);
          border: 1px solid var(--danger);
          border-left-width: 3px;
          border-radius: 6px;
          padding: 12px 16px;
          box-shadow: var(--shadow);
        }
        .alert-row.resolved { border-color: var(--border); opacity: 0.65; }
        .alert-row-main { display: flex; align-items: center; gap: 14px; font-size: 12.5px; color: var(--text-muted); }
        .alert-badge {
          background: var(--danger-dim);
          color: #9c2f28;
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.03em;
          padding: 3px 8px;
          border-radius: 999px;
        }
        .alert-tx { color: var(--text); font-weight: 600; }
        .alert-amount { color: var(--text); }
        .alert-score { color: var(--danger); font-weight: 600; }
        .alert-row-side { display: flex; align-items: center; gap: 12px; }
        .alert-time { font-size: 11px; color: var(--text-faint); }
        .alert-status-done { font-size: 11.5px; color: var(--success); font-weight: 600; }
        .btn-resolve {
          background: var(--panel-2);
          border: 1px solid var(--border);
          color: var(--text);
          font-size: 11.5px;
          padding: 6px 12px;
          border-radius: 4px;
          cursor: pointer;
        }
        .btn-resolve:hover { border-color: var(--accent-dim); }

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
        .login-screen {
          width: 100%;
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          background: linear-gradient(150deg, var(--sb-bg-1, #081617) 0%, var(--sb-bg-2, #0c3a3b) 48%, var(--sb-bg-3, #12ab8d) 100%);
        }
        .login-card {
          width: 360px;
          background: var(--panel, #ffffff);
          border-radius: 8px;
          box-shadow: var(--shadow, 0 1px 2px rgba(16,24,40,0.04), 0 4px 10px rgba(16,24,40,0.05));
          padding: 32px 30px;
        }
        .login-brand {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 26px;
        }
        .login-brand-mark {
          width: 36px; height: 36px;
          border-radius: 4px;
          background: var(--panel-2, #f5f7fa);
          border: 1px solid var(--accent-dim, #7fa9c4);
          display: flex; align-items: center; justify-content: center;
          color: var(--accent, #2e6b93);
        }
        .login-brand-name { font-family: 'Fraunces', serif; font-size: 17px; font-weight: 500; color: var(--text, #1c2430); }
        .login-brand-sub { font-size: 11px; color: var(--text-faint, #98a2b3); }
        .login-field { margin-bottom: 14px; }
        .login-label { display: block; font-size: 11.5px; color: var(--text-muted, #667085); margin-bottom: 6px; }
        .login-input {
          width: 100%;
          background: var(--panel, #ffffff);
          border: 1px solid var(--border, #e1e5eb);
          border-radius: 4px;
          padding: 10px 12px;
          font-size: 13.5px;
          color: var(--text, #1c2430);
          box-sizing: border-box;
        }
        .login-input:focus { outline: none; border-color: var(--accent-dim, #7fa9c4); }
        .login-error {
          background: var(--danger-dim, #fbe4e2);
          border: 1px solid var(--danger, #d6453d);
          color: #9c2f28;
          padding: 9px 12px;
          border-radius: 4px;
          font-size: 12px;
          margin-bottom: 14px;
        }
        .login-submit {
          width: 100%;
          background: var(--accent, #2e6b93);
          color: var(--on-accent, #ffffff);
          border: none;
          padding: 12px 16px;
          border-radius: 4px;
          font-size: 13.5px;
          font-weight: 600;
          cursor: pointer;
          margin-top: 6px;
        }
        .login-submit:disabled { opacity: 0.6; cursor: default; }
        .logout-btn {
          background: none;
          border: none;
          color: var(--sb-text-faint, #6f9c95);
          font-size: 11px;
          cursor: pointer;
          text-decoration: underline;
          margin-top: 8px;
          padding: 0;
        }
        .logout-btn:hover { color: var(--sb-text, #f0f9f7); }
      `}</style>

      {!isAuthenticated ? (
        <div className="login-screen">
          <div className="login-card">
            <div className="login-brand">
              <div className="login-brand-mark"><ShieldCheck size={18} /></div>
              <div>
                <div className="login-brand-name">Vigie</div>
                <div className="login-brand-sub">Détection de fraude</div>
              </div>
            </div>
            {loginError && <div className="login-error">{loginError}</div>}
            <form onSubmit={handleLogin}>
              <div className="login-field">
                <label className="login-label">Identifiant</label>
                <input
                  type="text"
                  className="login-input"
                  value={loginUsername}
                  onChange={(e) => setLoginUsername(e.target.value)}
                  autoComplete="username"
                />
              </div>
              <div className="login-field">
                <label className="login-label">Mot de passe</label>
                <input
                  type="password"
                  className="login-input"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  autoComplete="current-password"
                />
              </div>
              <button type="submit" className="login-submit" disabled={loginLoading}>
                {loginLoading ? 'Connexion…' : 'Se connecter'}
              </button>
            </form>
          </div>
        </div>
      ) : (
        <>
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
            <button type="button" className="logout-btn" onClick={handleLogout}>Se déconnecter</button>
          </div>
        </div>
      </aside>

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

          {activeTab === 'dg' && (
            <div>
              <div className="section-head">
                <h2 className="section-title">Indicateurs clés de performance</h2>
                <p className="section-desc">Vue d'ensemble des métriques de fraude et transactions enregistrées.</p>
              </div>
              <IndicatorsView />
            </div>
          )}

          {activeTab === 'risk' && (
            <div>
              <div className="section-head">
                <div className="section-title">Simulateur de score de risque</div>
                <div className="section-desc">Renseignez les caractéristiques d'une transaction, puis cliquez sur "Analyser" pour interroger le vrai modèle.</div>
              </div>

              <div className="risk-grid">
                <div className="risk-panel">
                  <div className="risk-panel-title">Paramètres de la transaction</div>

                  <div className="sample-tx-block">
                    <div className="sample-tx-head">
                      <span>Charger une vraie transaction</span>
                      <button type="button" className="icon-btn" onClick={loadSampleTransactions} disabled={samplesLoading}>
                        {samplesLoading ? '…' : 'Charger'}
                      </button>
                    </div>
                    {samplesError && (
                      <p className="sample-tx-error">
                        <AlertTriangle size={12} /> API indisponible ({samplesError}) — <code className="mono">GET {API_BASE_URL}/sample-transactions</code>
                      </p>
                    )}
                    {sampleTransactions.length > 0 && (
                      <div className="sample-tx-list">
                        {sampleTransactions.map(tx => (
                          <button
                            type="button"
                            key={tx.transaction_id}
                            className={`sample-tx-row ${loadedTransaction?.transaction_id === tx.transaction_id ? 'active' : ''}`}
                            onClick={() => applySampleTransaction(tx)}
                          >
                            <span className="mono">{tx.transaction_id}</span>
                            <span className="mono">{tx.amount.toLocaleString('fr-FR')}</span>
                            <span>{tx.merchant_category}</span>
                            <span className={tx.is_fraud === 1 ? 'sample-tx-fraud' : 'sample-tx-ok'}>
                              {tx.is_fraud === 1 ? 'fraude réelle' : 'légitime'}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                    {loadedTransaction && (
                      <p className="sample-tx-loaded">
                        Transaction <strong className="mono">{loadedTransaction.transaction_id}</strong> chargée — étiquette réelle en base : <strong>{loadedTransaction.is_fraud === 1 ? 'FRAUDULEUSE' : 'LÉGITIME'}</strong>.
                      </p>
                    )}
                  </div>

                  <div className="field-group model-field">
                    <label className="field-label">Montant <span className="model-tag">colonne réelle</span></label>
                    <input type="number" className="field-input" value={amount} onChange={(e) => { setAmount(e.target.value); setLoadedTransaction(null); }} />
                  </div>

                  <div className="demo-fields-note">
                    Les 14 champs ci-dessous correspondent tous à de vraies colonnes de <code className="mono">bank_transactions_cleaned</code> et sont envoyés au vrai modèle.
                  </div>

                  <div className="field-row">
                    <div className="field-group">
                      <label className="field-label">Type de commerçant</label>
                      <select className="field-select" value={merchantType} onChange={(e) => setMerchantType(e.target.value)}>
                        {MERCHANT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                      </select>
                    </div>
                    <div className="field-group">
                      <label className="field-label">Devise</label>
                      <select className="field-select" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                        {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </div>
                  </div>

                  <div className="field-row">
                    <div className="field-group">
                      <label className="field-label">Pays</label>
                      <select className="field-select" value={country} onChange={(e) => setCountry(e.target.value)}>
                        {COUNTRIES.map(c => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </div>
                    <div className="field-group">
                      <label className="field-label">Taille de ville</label>
                      <select className="field-select" value={citySize} onChange={(e) => setCitySize(e.target.value)}>
                        {CITY_SIZES.map(c => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </div>
                  </div>

                  <div className="field-row">
                    <div className="field-group">
                      <label className="field-label">Type de carte</label>
                      <select className="field-select" value={cardType} onChange={(e) => setCardType(e.target.value)}>
                        {CARD_TYPES.map(c => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </div>
                    <div className="field-group">
                      <label className="field-label">Appareil</label>
                      <select className="field-select" value={device} onChange={(e) => setDevice(e.target.value)}>
                        {DEVICES.map(d => <option key={d} value={d}>{d}</option>)}
                      </select>
                    </div>
                  </div>

                  <div className="field-row">
                    <div className="field-group">
                      <label className="field-label">Canal</label>
                      <select className="field-select" value={channel} onChange={(e) => setChannel(e.target.value)}>
                        {CHANNELS.map(c => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </div>
                    <div className="field-group">
                      <label className="field-label">Vélocité (transactions dans l'heure précédente)</label>
                      <input type="number" min="0" className="field-input" value={velocityLastHour} onChange={(e) => setVelocityLastHour(e.target.value)} />
                    </div>
                  </div>

                  <div className="field-group">
                    <label className="field-label">Heure de la transaction (0h–23h)</label>
                    <div className="slider-row">
                      <input type="range" min="0" max="23" value={transactionHour} onChange={(e) => setTransactionHour(e.target.value)} className="slider" />
                      <span className="slider-value mono">{transactionHour}</span>
                      <button type="button" className="icon-btn" onClick={() => setTransactionHour(12)} title="Réinitialiser"><RotateCcw size={13} /></button>
                    </div>
                  </div>

                  <div className="field-row">
                    <div className="field-group">
                      <label className="field-label">Carte présente</label>
                      <div className="radio-group">
                        <label className={`radio-pill ${Number(cardPresent) === 0 ? 'checked' : ''}`}>
                          <input type="radio" name="cardPresent" checked={Number(cardPresent) === 0} onChange={() => setCardPresent(0)} /> Non
                        </label>
                        <label className={`radio-pill ${Number(cardPresent) === 1 ? 'checked' : ''}`}>
                          <input type="radio" name="cardPresent" checked={Number(cardPresent) === 1} onChange={() => setCardPresent(1)} /> Oui
                        </label>
                      </div>
                    </div>
                    <div className="field-group">
                      <label className="field-label">Week-end</label>
                      <div className="radio-group">
                        <label className={`radio-pill ${Number(weekendTransaction) === 0 ? 'checked' : ''}`}>
                          <input type="radio" name="weekend" checked={Number(weekendTransaction) === 0} onChange={() => setWeekendTransaction(0)} /> Non
                        </label>
                        <label className={`radio-pill ${Number(weekendTransaction) === 1 ? 'checked' : ''}`}>
                          <input type="radio" name="weekend" checked={Number(weekendTransaction) === 1} onChange={() => setWeekendTransaction(1)} /> Oui
                        </label>
                      </div>
                    </div>
                  </div>

                  <div className="field-group">
                    <label className="field-label">Commerçant à risque élevé</label>
                    <div className="radio-group">
                      <label className={`radio-pill ${Number(highRiskMerchant) === 0 ? 'checked' : ''}`}>
                        <input type="radio" name="highRisk" checked={Number(highRiskMerchant) === 0} onChange={() => setHighRiskMerchant(0)} /> Non
                      </label>
                      <label className={`radio-pill ${Number(highRiskMerchant) === 1 ? 'checked' : ''}`}>
                        <input type="radio" name="highRisk" checked={Number(highRiskMerchant) === 1} onChange={() => setHighRiskMerchant(1)} /> Oui
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
                      {loadedTransaction && loadedTransaction.amount === Number(amount) && (
                        <div className={`ground-truth-note ${
                          (loadedTransaction.is_fraud === 1 ? 'FRAUDULEUSE' : 'LÉGITIME') === apiResult.decision ? 'match' : 'mismatch'
                        }`}>
                          Étiquette réelle en base : <strong>{loadedTransaction.is_fraud === 1 ? 'FRAUDULEUSE' : 'LÉGITIME'}</strong> — {
                            (loadedTransaction.is_fraud === 1 ? 'FRAUDULEUSE' : 'LÉGITIME') === apiResult.decision
                              ? 'le modèle est d\'accord avec la vérité terrain.'
                              : 'le modèle diverge de la vérité terrain sur cette transaction.'
                          }
                        </div>
                      )}
                    </>
                  )}

                  {!apiError && !(apiResult && apiResult.source === 'api') && (
                    <div className="placeholder-block" style={{ padding: '36px 20px' }}>
                      <Gauge size={24} style={{ color: 'var(--text-faint)', margin: '0 auto 10px auto' }} />
                      <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                        Cliquez sur "Analyser la transaction" pour interroger le vrai modèle.
                      </p>
                    </div>
                  )}

                  {apiError && (
                    <>
                      <div className="api-warning">
                        <AlertTriangle size={14} />
                        <span>API modèle indisponible ({apiError}) — <code className="mono">POST {API_BASE_URL}/predict-fraud</code> ne répond pas. Résultat de secours ci-dessous, calculé localement (pas le vrai modèle).</span>
                      </div>

                      <div className="local-preview-head">
                        Estimation locale (secours, API indisponible)
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
                    </>
                  )}
                </div>
              </div>

              <div className="disclaimer-banner">
                <Info size={15} />
                <span><strong>Note :</strong> le bouton "Analyser la transaction" envoie les 14 champs à <code className="mono">POST {API_BASE_URL}/predict-fraud</code>, qui reproduit le même encodage qu'à l'entraînement (via <code className="mono">model_columns.json</code>) avant d'interroger votre modèle XGBoost. L'estimation locale n'apparaît que si cette API ne répond pas, comme filet de secours clairement identifié — plus jamais affichée en permanence à côté du vrai résultat.</span>
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

              <div className="section-head" style={{ marginTop: 28 }}>
                <div className="section-title" style={{ fontSize: 15 }}>Documents indexés</div>
                <div className="section-desc">Retirez un document si vous ne voulez plus que l'assistant s'appuie sur lui.</div>
              </div>

              {documentsError && (
                <div className="api-warning">
                  <AlertTriangle size={14} />
                  <span>API indisponible ({documentsError}) — <code className="mono">GET {API_BASE_URL}/documents</code></span>
                </div>
              )}

              {!documentsError && documents.length === 0 && (
                <div className="placeholder-block" style={{ padding: '36px 20px' }}>
                  <FileText size={24} style={{ color: 'var(--text-faint)', margin: '0 auto 10px auto' }} />
                  <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>Aucun document envoyé pour l'instant.</p>
                </div>
              )}

              {documents.length > 0 && (
                <div className="ledger">
                  <div className="ledger-head">
                    <span>{documents.length} document(s)</span>
                  </div>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Fichier</th>
                        <th>Taille</th>
                        <th>Statut</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {documents.map(doc => (
                        <tr key={doc.filename}>
                          <td style={{ fontFamily: 'IBM Plex Sans' }}>{doc.filename}</td>
                          <td>{(doc.size_bytes / 1024).toFixed(1)} Ko</td>
                          <td>
                            {doc.indexed
                              ? <span className="sample-tx-ok">indexé</span>
                              : <span style={{ color: 'var(--text-faint)' }}>non indexé (format non pris en charge)</span>}
                          </td>
                          <td>
                            <button
                              type="button"
                              className="btn-resolve"
                              onClick={() => removeDocument(doc.filename)}
                              disabled={removingDoc === doc.filename}
                            >
                              {removingDoc === doc.filename ? '…' : 'Retirer'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {activeTab === 'alerts' && (
            <div>
              <div className="section-head">
                <div className="section-title">Alertes de fraude</div>
                <div className="section-desc">
                  Surveillance simulée : de "nouvelles" transactions sont rejouées depuis l'historique et scorées automatiquement par le vrai modèle. Toute transaction jugée frauduleuse crée une alerte ici, sans action manuelle.
                </div>
              </div>

              <div className="monitor-bar">
                <button
                  type="button"
                  className={`btn-monitor ${liveMonitoring ? 'active' : ''}`}
                  onClick={() => setLiveMonitoring(m => !m)}
                >
                  <span className={`monitor-dot ${liveMonitoring ? 'live' : ''}`} />
                  {liveMonitoring ? 'Surveillance en cours — arrêter' : 'Démarrer la surveillance en direct'}
                </button>
                <div className="monitor-stats">
                  <span><strong>{liveStats.processed}</strong> transactions analysées</span>
                  <span className="monitor-stats-sep">·</span>
                  <span className="monitor-stats-blocked"><strong>{liveStats.blocked}</strong> bloquées</span>
                </div>
              </div>

              <div className="disclaimer-banner">
                <Info size={15} />
                <span><strong>Simulation, pas une vraie connexion bancaire :</strong> il n'existe aucun flux de transactions en direct réel ici — le bouton ci-dessus rejoue des lignes historiques au hasard toutes les 4 secondes, comme si elles venaient d'être soumises, pour démontrer le principe de blocage automatique.</span>
              </div>

              {alertsError && (
                <div className="api-warning" style={{ marginTop: 16 }}>
                  <AlertTriangle size={14} />
                  <span>API indisponible ({alertsError}) — <code className="mono">GET {API_BASE_URL}/alerts</code></span>
                </div>
              )}

              {!alertsError && alerts.length === 0 && (
                <div className="placeholder-block" style={{ marginTop: 16 }}>
                  <AlertTriangle size={28} style={{ color: 'var(--text-faint)', margin: '0 auto 12px auto' }} />
                  <p style={{ fontSize: 14, fontWeight: 500, marginBottom: 4 }}>Aucune alerte pour l'instant</p>
                  <p style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Démarrez la surveillance en direct pour en générer.</p>
                </div>
              )}

              {alerts.length > 0 && (
                <div className="alert-list">
                  {alerts.map(a => (
                    <div key={a.id} className={`alert-row ${a.status === 'Traitée' ? 'resolved' : ''}`}>
                      <div className="alert-row-main">
                        <span className="alert-badge">BLOQUÉE</span>
                        <span className="mono alert-tx">{a.transaction_id}</span>
                        <span className="mono alert-amount">{a.amount.toLocaleString('fr-FR')}</span>
                        <span className="alert-score mono">{(a.probability * 100).toFixed(1)}%</span>
                        <span className={a.is_fraud_real === 1 ? 'sample-tx-fraud' : 'sample-tx-ok'}>
                          {a.is_fraud_real === 1 ? 'confirmée en base' : 'vérité terrain : légitime'}
                        </span>
                      </div>
                      <div className="alert-row-side">
                        <span className="alert-time">{new Date(a.created_at).toLocaleTimeString('fr-FR')}</span>
                        {a.status === 'Traitée' ? (
                          <span className="alert-status-done">Traitée</span>
                        ) : (
                          <button type="button" className="btn-resolve" onClick={() => resolveAlert(a.id)}>Marquer comme traité</button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

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
        </>
      )}
    </div>
  );
}

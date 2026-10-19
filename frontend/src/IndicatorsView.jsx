import React, { useEffect, useState } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const API_BASE_URL = "http://localhost:8000/api/v1";
const COLORS = ['#2e6b93', '#d6453d', '#2f9e6e', '#f59e0b', '#8b5cf6'];

export default function IndicatorsView() {
  const [kpi, setKpi] = useState(null);
  const [indicators, setIndicators] = useState({ by_channel: [], by_merchant: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 1. Correction du nom de l'endpoint : dashboard-kpis au lieu de kpi-stats
    const fetchKpi = fetch(`${API_BASE_URL}/dashboard-kpis`)
      .then(r => r.ok ? r.json() : null)
      .catch(() => null);

    const fetchIndicators = fetch(`${API_BASE_URL}/decision-indicators`)
      .then(r => r.ok ? r.json() : { by_channel: [], by_merchant: [] })
      .catch(() => ({ by_channel: [], by_merchant: [] }));

    Promise.all([fetchKpi, fetchIndicators])
      .then(([kpiData, indData]) => {
        if (kpiData) setKpi(kpiData);
        if (indData) {
          setIndicators({
            by_channel: Array.isArray(indData?.by_channel) ? indData.by_channel : [],
            by_merchant: Array.isArray(indData?.by_merchant) ? indData.by_merchant : []
          });
        }
      })
      .catch(err => console.error("Erreur de chargement :", err))
      .finally(() => setLoading(false));
  }, []);

  // 2. Correction des clés d'accès JSON renvoyées par FastAPI
  const totalTx = Number(kpi?.total_transactions || 0).toLocaleString('fr-FR');
  const totalFrauds = Number(kpi?.fraudes_detectees || 0).toLocaleString('fr-FR');
  const fraudRate = kpi?.taux_fraude !== undefined ? `${kpi.taux_fraude}%` : "—";
  
  // 3. Remplacement de l'Euro (€) par le Franc CFA (XOF)
  const totalFraudAmount = Number(kpi?.montant_total_fraude || 0).toLocaleString('fr-FR');
  const currency = kpi?.currency || 'XOF';

  const channelData = Array.isArray(indicators?.by_channel) ? indicators.by_channel : [];
  const merchantData = Array.isArray(indicators?.by_merchant) ? indicators.by_merchant : [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* 1. Cartes Métriques */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
        <div style={cardStyle}>
          <span style={labelStyle}>Total Transactions</span>
          <h2 style={valueStyle}>{totalTx}</h2>
        </div>
        <div style={cardStyle}>
          <span style={labelStyle}>Fraudes Détectées</span>
          <h2 style={{ ...valueStyle, color: '#d6453d' }}>{totalFrauds}</h2>
        </div>
        <div style={cardStyle}>
          <span style={labelStyle}>Taux de Fraude</span>
          <h2 style={valueStyle}>{fraudRate}</h2>
        </div>
        <div style={cardStyle}>
          <span style={labelStyle}>Montant Total Fraudé</span>
          <h2 style={{ ...valueStyle, color: '#d6453d' }}>{totalFraudAmount} {currency}</h2>
        </div>
      </div>

      {/* 2. Graphiques Décisionnels */}
      <div style={{ background: '#fff', padding: '24px', borderRadius: '8px', border: '1px solid #e1e5eb' }}>
        <h3 style={{ margin: '0 0 4px 0', fontSize: '16px' }}>Indicateurs décisionnels</h3>
        <p style={{ color: '#667085', fontSize: '13px', margin: '0 0 24px 0' }}>
          Tendances financières et répartition de la fraude par canal et marchand.
        </p>

        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#667085' }}>Chargement depuis la base...</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', height: '320px' }}>
            
            {/* Camembert 1 : Fraudes par Canal */}
            <div>
              <h4 style={{ fontSize: '13px', color: '#667085', marginBottom: '12px', textAlign: 'center' }}>
                Répartition des Fraudes par Canal
              </h4>
              <ResponsiveContainer width="100%" height="85%">
                <PieChart>
                  <Pie data={channelData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                    {channelData.map((_, index) => (
                      <Cell key={`cell-ch-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* Camembert 2 : Top Marchands */}
            <div>
              <h4 style={{ fontSize: '13px', color: '#667085', marginBottom: '12px', textAlign: 'center' }}>
                Top Marchands Touchés
              </h4>
              <ResponsiveContainer width="100%" height="85%">
                <PieChart>
                  <Pie data={merchantData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                    {merchantData.map((_, index) => (
                      <Cell key={`cell-mch-${index}`} fill={COLORS[(index + 2) % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>

          </div>
        )}
      </div>

    </div>
  );
}

const cardStyle = { background: '#fff', padding: '16px', borderRadius: '8px', border: '1px solid #e1e5eb' };
const labelStyle = { fontSize: '12px', color: '#667085' };
const valueStyle = { fontSize: '20px', fontWeight: '600', margin: '8px 0 0 0' };
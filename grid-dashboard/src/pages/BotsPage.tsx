import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { BotRegistrationResponse, DispatchReceiptResponse, CreateBotRequest } from '../types/dashboard';
import {
  Bot,
  Plus,
  Trash2,
  Zap,
  Activity,
  CheckCircle,
  AlertCircle,
  X,
  Radio,
} from 'lucide-react';

export const BotsPage: React.FC = () => {
  const [bots, setBots] = useState<BotRegistrationResponse[]>([]);
  const [logs, setLogs] = useState<DispatchReceiptResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [pingingBotId, setPingingBotId] = useState<string | null>(null);
  const [pingResult, setPingResult] = useState<{ botId: string; status: string; latency: number } | null>(null);
  const [showAddModal, setShowAddModal] = useState<boolean>(false);

  // Form state for creating a new bot
  const [formData, setFormData] = useState<CreateBotRequest>({
    name: '',
    target_broker: 'Zerodha',
    webhook_url: '',
    secret_key: '',
    subscribed_setups: ['ALL'],
    min_confidence_score: 80.0,
    is_active: true,
  });

  const fetchData = async () => {
    setLoading(true);
    try {
      const [bList, lList] = await Promise.all([
        api.getRegisteredBots(),
        api.getDispatchLogs(50),
      ]);
      setBots(bList);
      setLogs(lList);
    } catch (err) {
      console.error('Failed to load execution bots data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleTestPing = async (botId: string) => {
    setPingingBotId(botId);
    setPingResult(null);
    try {
      const res = await api.testPingBot(botId);
      setPingResult({
        botId,
        status: res.status,
        latency: res.latency_ms,
      });
      // Refresh delivery logs
      const updatedLogs = await api.getDispatchLogs(50);
      setLogs(updatedLogs);
    } catch (err: any) {
      setPingResult({
        botId,
        status: 'FAILED',
        latency: 0,
      });
    } finally {
      setPingingBotId(null);
    }
  };

  const handleDeleteBot = async (botId: string) => {
    if (!window.confirm('Are you sure you want to unregister this execution bot?')) return;
    try {
      await api.deleteBot(botId);
      setBots(bots.filter((b) => b.bot_id !== botId));
    } catch (err) {
      console.error('Failed to delete bot:', err);
    }
  };

  const handleCreateBot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.webhook_url) return;

    try {
      const newBot = await api.registerBot(formData);
      setBots([newBot, ...bots]);
      setShowAddModal(false);
      setFormData({
        name: '',
        target_broker: 'Zerodha',
        webhook_url: '',
        secret_key: '',
        subscribed_setups: ['ALL'],
        min_confidence_score: 80.0,
        is_active: true,
      });
    } catch (err: any) {
      alert(`Error registering bot: ${err.message}`);
    }
  };

  const activeBotsCount = bots.filter((b) => b.is_active).length;
  const successfulDispatches = logs.filter((l) => l.status === 'SUCCESS').length;
  const dispatchSuccessRate = logs.length > 0 ? (successfulDispatches / logs.length) * 100 : 100;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Header Banner */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          backgroundColor: '#1F2937',
          padding: '16px 20px',
          borderRadius: '12px',
          border: '1px solid #374151',
          gap: '12px',
        }}
      >
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#F9FAFB', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Bot size={22} color="#60A5FA" /> Master Signal Dispatcher &amp; Execution Bots
          </h2>
          <p style={{ fontSize: '13px', color: '#9CA3AF', margin: '4px 0 0 0' }}>
            Broadcasting HMAC-SHA256 verified trade instructions to independent worker bots (Zerodha, Dhan, Fyers, Custom)
          </p>
        </div>

        <button
          onClick={() => setShowAddModal(true)}
          style={{
            backgroundColor: '#2563EB',
            color: '#FFFFFF',
            border: 'none',
            borderRadius: '8px',
            padding: '8px 16px',
            fontSize: '13px',
            fontWeight: 700,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Plus size={16} /> Register Execution Bot
        </button>
      </div>

      {/* Metrics Banner */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
        <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
          <div style={{ fontSize: '11px', color: '#9CA3AF' }}>REGISTERED WORKER BOTS</div>
          <div style={{ fontSize: '22px', fontWeight: 800, color: '#F9FAFB', marginTop: '2px' }}>{bots.length}</div>
        </div>

        <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
          <div style={{ fontSize: '11px', color: '#9CA3AF' }}>ACTIVE WEBHOOKS</div>
          <div style={{ fontSize: '22px', fontWeight: 800, color: '#10B981', marginTop: '2px' }}>{activeBotsCount} Active</div>
        </div>

        <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
          <div style={{ fontSize: '11px', color: '#9CA3AF' }}>WEBSOCKET FEED</div>
          <div style={{ fontSize: '14px', fontWeight: 800, color: '#60A5FA', marginTop: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Radio size={14} className="spin" /> /api/v1/dispatch/stream
          </div>
        </div>

        <div style={{ backgroundColor: '#1F2937', padding: '14px', borderRadius: '8px', border: '1px solid #374151' }}>
          <div style={{ fontSize: '11px', color: '#9CA3AF' }}>DISPATCH SUCCESS RATE</div>
          <div style={{ fontSize: '22px', fontWeight: 800, color: dispatchSuccessRate >= 90 ? '#10B981' : '#F59E0B', marginTop: '2px' }}>
            {dispatchSuccessRate.toFixed(1)}%
          </div>
        </div>
      </div>

      {/* Connected Bots List */}
      <div style={{ backgroundColor: '#1F2937', padding: '20px', borderRadius: '12px', border: '1px solid #374151' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#F9FAFB', marginBottom: '16px' }}>
          Connected Downstream Execution Bots
        </h3>

        {bots.length > 0 ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
            {bots.map((b) => (
              <div
                key={b.bot_id}
                style={{
                  backgroundColor: '#111827',
                  border: '1px solid #374151',
                  borderRadius: '10px',
                  padding: '16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '15px', fontWeight: 800, color: '#F9FAFB' }}>{b.name}</span>
                      <span
                        style={{
                          fontSize: '10px',
                          padding: '2px 6px',
                          backgroundColor: '#1E3A8A',
                          color: '#93C5FD',
                          borderRadius: '4px',
                          fontWeight: 700,
                        }}
                      >
                        {b.target_broker}
                      </span>
                    </div>
                    <span style={{ fontSize: '11px', color: '#6B7280' }}>ID: {b.bot_id}</span>
                  </div>

                  <span
                    style={{
                      fontSize: '10px',
                      padding: '3px 8px',
                      borderRadius: '12px',
                      fontWeight: 700,
                      backgroundColor: b.is_active ? '#064E3B' : '#374151',
                      color: b.is_active ? '#34D399' : '#9CA3AF',
                    }}
                  >
                    {b.is_active ? '🟢 ACTIVE' : '⚪ DISABLED'}
                  </span>
                </div>

                {/* Webhook URL snippet */}
                <div
                  style={{
                    backgroundColor: '#1F2937',
                    padding: '8px 10px',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontFamily: 'monospace',
                    color: '#D1D5DB',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  title={b.webhook_url}
                >
                  {b.webhook_url}
                </div>

                {/* Subscriptions & Threshold */}
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#9CA3AF' }}>
                  <span>
                    Min Score: <strong style={{ color: '#F9FAFB' }}>{b.min_confidence_score} pts</strong>
                  </span>
                  <span>
                    Setups: <strong style={{ color: '#60A5FA' }}>{b.subscribed_setups.join(', ')}</strong>
                  </span>
                </div>

                {/* Test Ping Status Feedback */}
                {pingResult && pingResult.botId === b.bot_id && (
                  <div
                    style={{
                      fontSize: '11px',
                      padding: '6px 10px',
                      borderRadius: '6px',
                      backgroundColor: pingResult.status === 'SUCCESS' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                      color: pingResult.status === 'SUCCESS' ? '#34D399' : '#FCA5A5',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    {pingResult.status === 'SUCCESS' ? <CheckCircle size={13} /> : <AlertCircle size={13} />}
                    {pingResult.status === 'SUCCESS'
                      ? `Ping Successful (${pingResult.latency.toFixed(1)}ms)`
                      : 'Ping Failed (Check webhook URL or server)'}
                  </div>
                )}

                {/* Action Buttons */}
                <div style={{ display: 'flex', gap: '8px', marginTop: 'auto', paddingTop: '8px', borderTop: '1px solid #1F2937' }}>
                  <button
                    onClick={() => handleTestPing(b.bot_id)}
                    disabled={pingingBotId === b.bot_id}
                    style={{
                      flex: 1,
                      backgroundColor: '#374151',
                      border: 'none',
                      borderRadius: '6px',
                      color: '#F9FAFB',
                      padding: '6px 10px',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: pingingBotId === b.bot_id ? 'not-allowed' : 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '6px',
                    }}
                  >
                    <Zap size={13} color="#F59E0B" />
                    {pingingBotId === b.bot_id ? 'Testing...' : 'Test Ping Webhook'}
                  </button>

                  <button
                    onClick={() => handleDeleteBot(b.bot_id)}
                    style={{
                      backgroundColor: '#450A0A',
                      border: 'none',
                      borderRadius: '6px',
                      color: '#F87171',
                      padding: '6px 10px',
                      cursor: 'pointer',
                    }}
                    title="Unregister Bot"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ padding: '30px', textAlign: 'center', color: '#9CA3AF', border: '1px dashed #374151', borderRadius: '10px' }}>
            {loading ? 'Loading execution bots...' : 'No downstream execution bots registered yet. Click "+ Register Execution Bot" above.'}
          </div>
        )}
      </div>

      {/* Dispatch Delivery Audit Log */}
      <div style={{ backgroundColor: '#1F2937', padding: '20px', borderRadius: '12px', border: '1px solid #374151' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#F9FAFB', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={18} color="#10B981" /> Live Dispatch Delivery Receipts &amp; Latency Logs
        </h3>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #374151', color: '#9CA3AF' }}>
                <th style={{ padding: '10px' }}>TIMESTAMP</th>
                <th style={{ padding: '10px' }}>SIGNAL ID</th>
                <th style={{ padding: '10px' }}>BOT ID</th>
                <th style={{ padding: '10px' }}>STATUS</th>
                <th style={{ padding: '10px' }}>HTTP CODE</th>
                <th style={{ padding: '10px' }}>LATENCY</th>
                <th style={{ padding: '10px' }}>ERROR / DETAIL</th>
              </tr>
            </thead>
            <tbody>
              {logs.length > 0 ? (
                logs.map((l) => (
                  <tr
                    key={l.dispatch_id}
                    style={{
                      borderBottom: '1px solid #1F2937',
                      color: '#E5E7EB',
                    }}
                  >
                    <td style={{ padding: '10px', color: '#9CA3AF' }}>
                      {l.timestamp ? l.timestamp.slice(0, 19).replace('T', ' ') : '--'}
                    </td>
                    <td style={{ padding: '10px', fontWeight: 700, color: '#60A5FA' }}>{l.signal_id}</td>
                    <td style={{ padding: '10px', fontFamily: 'monospace' }}>{l.bot_id}</td>
                    <td style={{ padding: '10px' }}>
                      <span
                        style={{
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontSize: '10px',
                          fontWeight: 700,
                          backgroundColor: l.status === 'SUCCESS' ? '#064E3B' : '#450A0A',
                          color: l.status === 'SUCCESS' ? '#34D399' : '#F87171',
                        }}
                      >
                        {l.status}
                      </span>
                    </td>
                    <td style={{ padding: '10px', fontWeight: 600 }}>{l.response_code || '--'}</td>
                    <td style={{ padding: '10px', color: '#D1D5DB' }}>{l.latency_ms.toFixed(1)} ms</td>
                    <td style={{ padding: '10px', color: l.error_message ? '#FCA5A5' : '#9CA3AF' }}>
                      {l.error_message || 'Delivered successfully'}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '24px', color: '#9CA3AF' }}>
                    No automated dispatches recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add Bot Modal */}
      {showAddModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.75)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 99999,
            padding: '20px',
          }}
          onClick={() => setShowAddModal(false)}
        >
          <div
            style={{
              backgroundColor: '#111827',
              border: '1px solid #374151',
              borderRadius: '12px',
              width: '100%',
              maxWidth: '480px',
              padding: '24px',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: 800, color: '#F9FAFB', margin: 0 }}>
                Register Downstream Execution Bot
              </h3>
              <button
                onClick={() => setShowAddModal(false)}
                style={{ background: 'none', border: 'none', color: '#9CA3AF', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreateBot} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '4px' }}>
                  BOT NAME / LABEL
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Zerodha Kite Runner #1"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  style={{
                    width: '100%',
                    backgroundColor: '#1F2937',
                    border: '1px solid #374151',
                    borderRadius: '6px',
                    padding: '8px 12px',
                    color: '#F9FAFB',
                    fontSize: '13px',
                  }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '4px' }}>
                    TARGET BROKER
                  </label>
                  <select
                    value={formData.target_broker}
                    onChange={(e) => setFormData({ ...formData, target_broker: e.target.value })}
                    style={{
                      width: '100%',
                      backgroundColor: '#1F2937',
                      border: '1px solid #374151',
                      borderRadius: '6px',
                      padding: '8px 12px',
                      color: '#F9FAFB',
                      fontSize: '13px',
                    }}
                  >
                    <option value="Zerodha">Zerodha Kite</option>
                    <option value="Dhan">Dhan HQ</option>
                    <option value="Fyers">Fyers API</option>
                    <option value="AngelOne">Angel One SmartAPI</option>
                    <option value="Finvasia">Shoonya (Finvasia)</option>
                    <option value="Custom">Custom Python / Node Bot</option>
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '4px' }}>
                    MIN CONFIDENCE SCORE
                  </label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={formData.min_confidence_score}
                    onChange={(e) => setFormData({ ...formData, min_confidence_score: Number(e.target.value) })}
                    style={{
                      width: '100%',
                      backgroundColor: '#1F2937',
                      border: '1px solid #374151',
                      borderRadius: '6px',
                      padding: '8px 12px',
                      color: '#F9FAFB',
                      fontSize: '13px',
                    }}
                  />
                </div>
              </div>

              <div>
                <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '4px' }}>
                  WEBHOOK DESTINATION URL (HTTP POST)
                </label>
                <input
                  type="url"
                  required
                  placeholder="https://my-execution-bot.com/webhook/signals"
                  value={formData.webhook_url}
                  onChange={(e) => setFormData({ ...formData, webhook_url: e.target.value })}
                  style={{
                    width: '100%',
                    backgroundColor: '#1F2937',
                    border: '1px solid #374151',
                    borderRadius: '6px',
                    padding: '8px 12px',
                    color: '#F9FAFB',
                    fontSize: '13px',
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: '11px', color: '#9CA3AF', display: 'block', marginBottom: '4px' }}>
                  HMAC-SHA256 SECRET KEY (Optional, auto-generated if blank)
                </label>
                <input
                  type="text"
                  placeholder="Leave empty for auto-generated secret"
                  value={formData.secret_key}
                  onChange={(e) => setFormData({ ...formData, secret_key: e.target.value })}
                  style={{
                    width: '100%',
                    backgroundColor: '#1F2937',
                    border: '1px solid #374151',
                    borderRadius: '6px',
                    padding: '8px 12px',
                    color: '#F9FAFB',
                    fontSize: '13px',
                  }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  style={{
                    backgroundColor: '#374151',
                    border: 'none',
                    borderRadius: '6px',
                    padding: '8px 16px',
                    color: '#D1D5DB',
                    fontSize: '13px',
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  style={{
                    backgroundColor: '#2563EB',
                    border: 'none',
                    borderRadius: '6px',
                    padding: '8px 20px',
                    color: '#FFFFFF',
                    fontWeight: 700,
                    fontSize: '13px',
                    cursor: 'pointer',
                  }}
                >
                  Register Bot
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

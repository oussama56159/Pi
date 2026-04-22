import { useState } from 'react';
import {
  Shield, Server, Database, Cpu, HardDrive, Activity,
  RefreshCw, Download, Trash2, Clock, CheckCircle, AlertTriangle,
} from 'lucide-react';
import Card, { CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';

const systemHealth = [
  { name: 'API Server', status: 'healthy', uptime: '99.97%', latency: '12ms', icon: Server },
  { name: 'PostgreSQL', status: 'healthy', uptime: '99.99%', latency: '3ms', icon: Database },
  { name: 'In-Memory Cache', status: 'healthy', uptime: '100%', latency: '0.1ms', icon: Cpu },
  { name: 'MQTT Broker', status: 'healthy', uptime: '99.98%', latency: '2ms', icon: Activity },
  { name: 'WebSocket Gateway', status: 'healthy', uptime: '99.90%', latency: '15ms', icon: Activity },
];

const auditLogs = [
  { id: 1, user: 'Admin Operator', action: 'Vehicle ARM command', target: 'Eagle-01', timestamp: '2026-02-07T10:15:00Z', level: 'warning' },
  { id: 2, user: 'Sarah Chen', action: 'Mission uploaded', target: 'Perimeter Survey Alpha', timestamp: '2026-02-07T09:45:00Z', level: 'info' },
  { id: 3, user: 'System', action: 'Firmware update available', target: 'Shadow-05', timestamp: '2026-02-07T08:30:00Z', level: 'info' },
  { id: 4, user: 'Admin Operator', action: 'User role changed', target: 'James Park → Admin', timestamp: '2026-02-06T16:20:00Z', level: 'warning' },
  { id: 5, user: 'System', action: 'Emergency stop triggered', target: 'Osprey-07', timestamp: '2026-02-06T14:05:00Z', level: 'critical' },
  { id: 6, user: 'Marcus Williams', action: 'Fleet config updated', target: 'Bravo Team', timestamp: '2026-02-06T11:30:00Z', level: 'info' },
];

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState('health');

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Admin Panel</h1>
          <p className="text-sm text-slate-400 mt-1">System administration and monitoring</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" icon={Download}>Export Logs</Button>
          <Button variant="secondary" size="sm" icon={RefreshCw}>Refresh</Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-800 pb-px">
        {['health', 'audit', 'config'].map((tab) => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400 hover:text-slate-300'
            }`}>
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* System Health */}
      {activeTab === 'health' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {systemHealth.map((service) => {
              const Icon = service.icon;
              const isHealthy = service.status === 'healthy';
              return (
                <Card key={service.name}>
                  <div className="flex items-start gap-3">
                    <div className={`p-2 rounded-lg ${isHealthy ? 'bg-emerald-500/10' : 'bg-amber-500/10'}`}>
                      <Icon className={`w-5 h-5 ${isHealthy ? 'text-emerald-400' : 'text-amber-400'}`} />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-slate-200">{service.name}</p>
                        <Badge color={isHealthy ? 'green' : 'amber'} dot>{service.status}</Badge>
                      </div>
                      <div className="grid grid-cols-2 gap-2 mt-2">
                        <div><p className="text-[10px] text-slate-500 uppercase">Uptime</p><p className="text-xs font-mono text-slate-300">{service.uptime}</p></div>
                        <div><p className="text-[10px] text-slate-500 uppercase">Latency</p><p className="text-xs font-mono text-slate-300">{service.latency}</p></div>
                      </div>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
          <Card>
            <CardHeader><CardTitle subtitle="Resource utilization">System Resources</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              {[
                { label: 'CPU Usage', value: 34, color: 'bg-blue-500' },
                { label: 'Memory Usage', value: 62, color: 'bg-purple-500' },
                { label: 'Disk Usage', value: 48, color: 'bg-amber-500' },
                { label: 'Network I/O', value: 21, color: 'bg-cyan-500' },
              ].map((res) => (
                <div key={res.label}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-400">{res.label}</span>
                    <span className="text-slate-200 font-mono">{res.value}%</span>
                  </div>
                  <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div className={`h-full ${res.color} rounded-full transition-all`} style={{ width: `${res.value}%` }} />
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Audit Logs */}
      {activeTab === 'audit' && (
        <Card padding={false}>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left text-xs uppercase tracking-wider text-slate-500 px-5 py-3">Time</th>
                  <th className="text-left text-xs uppercase tracking-wider text-slate-500 px-5 py-3">User</th>
                  <th className="text-left text-xs uppercase tracking-wider text-slate-500 px-5 py-3">Action</th>
                  <th className="text-left text-xs uppercase tracking-wider text-slate-500 px-5 py-3">Target</th>
                  <th className="text-left text-xs uppercase tracking-wider text-slate-500 px-5 py-3">Level</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.map((log) => (
                  <tr key={log.id} className="border-b border-slate-700/50 hover:bg-slate-700/20 transition-colors">
                    <td className="px-5 py-3 text-sm text-slate-400 font-mono whitespace-nowrap">{new Date(log.timestamp).toLocaleString()}</td>
                    <td className="px-5 py-3 text-sm text-slate-200">{log.user}</td>
                    <td className="px-5 py-3 text-sm text-slate-300">{log.action}</td>
                    <td className="px-5 py-3 text-sm text-slate-400">{log.target}</td>
                    <td className="px-5 py-3">
                      <Badge color={log.level === 'critical' ? 'red' : log.level === 'warning' ? 'amber' : 'blue'}>{log.level}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* System Config */}
      {activeTab === 'config' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader><CardTitle>MQTT Configuration</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {[['Broker URL', 'mqtt://emqx.aerocommand.io:1883'], ['Max Connections', '10,000'], ['QoS Level', '1 (At least once)'], ['Keep-alive', '60s']].map(([k, v]) => (
                <div key={k} className="flex justify-between p-2 bg-slate-700/30 rounded-lg">
                  <span className="text-sm text-slate-400">{k}</span><span className="text-sm text-slate-200 font-mono">{v}</span>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>MAVLink Configuration</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {[['Protocol Version', 'MAVLink 2.0'], ['System ID Range', '1-254'], ['Heartbeat Rate', '1 Hz'], ['Telemetry Rate', '10 Hz']].map(([k, v]) => (
                <div key={k} className="flex justify-between p-2 bg-slate-700/30 rounded-lg">
                  <span className="text-sm text-slate-400">{k}</span><span className="text-sm text-slate-200 font-mono">{v}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

    </div>
  );
}


import {
  Radar, Plane, Battery, Navigation, AlertTriangle,
  Wifi,
} from 'lucide-react';
import Card, { CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import StatusIndicator from '@/components/ui/StatusIndicator';
import { useFleetStore } from '@/stores/fleetStore';
import { useTelemetryStore } from '@/stores/telemetryStore';
import { useMissionStore } from '@/stores/missionStore';
import { useMemo } from 'react';
import { buildLiveOpsMetrics } from '@/lib/analytics/liveMetrics';

function StatCard({ icon: Icon, label, value, sub, color = 'blue' }) {
  const colors = { blue: 'from-blue-500 to-blue-600', green: 'from-emerald-500 to-emerald-600', red: 'from-red-500 to-red-600', amber: 'from-amber-500 to-amber-600', purple: 'from-purple-500 to-purple-600', cyan: 'from-cyan-500 to-cyan-600' };
  return (
    <Card className="relative overflow-hidden">
      <div className={`absolute top-0 right-0 w-20 h-20 bg-gradient-to-br ${colors[color]} opacity-10 rounded-bl-[40px]`} />
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-400">{label}</p>
          <p className="text-2xl font-bold text-slate-100 mt-1 telemetry-value">{value}</p>
          {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
        </div>
        <div className={`p-2.5 rounded-xl bg-gradient-to-br ${colors[color]} shadow-lg`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
      </div>
    </Card>
  );
}

function ActiveVehicleRow({ vehicle }) {
  const telemetry = useTelemetryStore((s) => s.vehicleTelemetry[vehicle.id]);
  const battery = telemetry?.battery ?? vehicle.battery;
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-700/30 transition-colors">
      <StatusIndicator status={vehicle.status} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-200 truncate">{vehicle.name}</p>
        <p className="text-xs text-slate-500">{vehicle.callsign} • {vehicle.type}</p>
      </div>
      <Badge status={vehicle.status} dot />
      <div className="text-right">
        <p className="text-sm font-mono text-slate-300">{Math.round(battery)}%</p>
        <p className="text-xs text-slate-500">{telemetry?.altitude?.toFixed(0) || 0}m</p>
      </div>
    </div>
  );
}

function getAlertTime(alert) {
  const rawTime = alert?.receivedAt || alert?.timestamp || alert?.created_at || alert?.createdAt;
  const parsed = rawTime ? new Date(rawTime) : new Date(0);
  return Number.isNaN(parsed.getTime()) ? new Date(0) : parsed;
}

function getAlertTitle(alert) {
  return alert?.title || alert?.subject || alert?.message || 'Notification';
}

function getAlertMessage(alert) {
  return alert?.message || '';
}

export default function DashboardPage() {
  const vehicles = useFleetStore((s) => s.vehicles);
  const alerts = useTelemetryStore((s) => s.alerts);
  const missions = useMissionStore((s) => s.missions);
  const telemetryByVehicle = useTelemetryStore((s) => s.vehicleTelemetry);
  const connectionStatus = useTelemetryStore((s) => s.connectionStatus);

  const metrics = useMemo(
    () => buildLiveOpsMetrics({ vehicles, missions, alerts, telemetryByVehicle, connectionStatus }),
    [vehicles, missions, alerts, telemetryByVehicle, connectionStatus]
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Operations Dashboard</h1>
        <p className="text-sm text-slate-400 mt-1">Real-time fleet overview and operations status</p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        <StatCard icon={Radar} label="Total Fleet" value={metrics.totalFleet} sub={`${metrics.onlineVehicles} online`} color="blue" />
        <StatCard icon={Wifi} label="Connected" value={metrics.connectedVehicles} sub="Live link" color="cyan" />
        <StatCard icon={Plane} label="In Flight" value={metrics.inFlightVehicles} sub="Active now" color="purple" />
        <StatCard icon={Navigation} label="Active Missions" value={metrics.activeMissions} sub={`${metrics.totalMissions} total`} color="purple" />
        <StatCard icon={AlertTriangle} label="Critical Alerts" value={metrics.criticalAlerts} sub={`${alerts.length} total`} color={metrics.criticalAlerts > 0 ? 'red' : 'green'} />
        <StatCard icon={Battery} label="Avg Battery" value={`${Math.round(metrics.averageBattery)}%`} sub={`${metrics.telemetrySampleCount} samples`} color="amber" />
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Active Vehicles */}
        <Card className="lg:col-span-2">
          <CardHeader action={<Badge color="blue">{metrics.connectedVehicles} connected</Badge>}>
            <CardTitle subtitle="Real-time status of fleet vehicles">Active Vehicles</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 max-h-[400px] overflow-y-auto">
            {vehicles
              .filter((v) => v.status !== 'offline')
              .map((v) => <ActiveVehicleRow key={v.id} vehicle={v} />)}
            {vehicles.filter((v) => v.status !== 'offline').length === 0 && (
              <p className="text-center text-sm text-slate-500 py-8">No active vehicles</p>
            )}
          </CardContent>
        </Card>

        {/* Recent Alerts */}
        <Card>
          <CardHeader action={<Badge color={metrics.criticalAlerts > 0 ? 'red' : 'green'}>{metrics.criticalAlerts} critical</Badge>}>
            <CardTitle subtitle="Latest system alerts">Alerts</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 max-h-[400px] overflow-y-auto">
            {alerts.slice(0, 8).map((alert) => (
              <div key={alert.id} className={`p-3 rounded-lg border ${
                alert.severity === 'critical' ? 'bg-red-500/5 border-red-500/20' :
                alert.severity === 'warning' ? 'bg-amber-500/5 border-amber-500/20' :
                'bg-blue-500/5 border-blue-500/20'
              }`}>
                <div className="flex items-start gap-2">
                  <AlertTriangle className={`w-4 h-4 mt-0.5 shrink-0 ${
                    alert.severity === 'critical' ? 'text-red-400' :
                    alert.severity === 'warning' ? 'text-amber-400' : 'text-blue-400'
                  }`} />
                  <div>
                    <p className="text-sm font-medium text-slate-200">{getAlertTitle(alert)}</p>
                    {getAlertMessage(alert) && (
                      <p className="text-sm text-slate-300 mt-1">{getAlertMessage(alert)}</p>
                    )}
                    <p className="text-xs text-slate-500 mt-1">{getAlertTime(alert).toLocaleString()}</p>
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}


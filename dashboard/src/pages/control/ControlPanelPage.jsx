import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ShieldCheck, ShieldOff, Plane, ArrowDownToLine, RotateCcw, OctagonX,
  Gauge, Radio, Gamepad2, AlertTriangle, ChevronDown,
} from 'lucide-react';
import Card, { CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import StatusIndicator from '@/components/ui/StatusIndicator';
import ActionButton from '@/components/actions/ActionButton';
import { useFleetStore } from '@/stores/fleetStore';
import { useTelemetryStore } from '@/stores/telemetryStore';
import { useUIStore } from '@/stores/uiStore';
import { useMissionStore } from '@/stores/missionStore';
import { COMMANDS, FLIGHT_MODES } from '@/config/constants';
import { useMissionStream } from '@/lib/websocket/useMissionStream';

function ControlActionButton({ actionId, icon: Icon, label, onAction, disabled, disabledReason }) {
  return (
    <ActionButton
      actionId={actionId}
      icon={Icon}
      size="md"
      disabled={disabled}
      disabledReason={disabledReason}
      onAction={onAction}
      className="flex-col h-auto py-4 gap-1.5"
    >
      <span className="text-xs">{label}</span>
    </ActionButton>
  );
}

export default function ControlPanelPage() {
  const vehiclesRaw = useFleetStore((s) => s.vehicles);
  const vehicles = useMemo(() => (Array.isArray(vehiclesRaw) ? vehiclesRaw : []), [vehiclesRaw]);
  const sendCommand = useFleetStore((s) => s.sendCommand);
  const telemetry = useTelemetryStore((s) => s.vehicleTelemetry) || {};
  const connectionStatus = useTelemetryStore((s) => s.connectionStatus) || {};
  const addToast = useUIStore((s) => s.addToast);
  const [selectedId, setSelectedId] = useState('');
  const getActiveMissionForVehicle = useMissionStore((s) => s.getActiveMissionForVehicle);
  const fetchMissions = useMissionStore((s) => s.fetchMissions);

  const activeVehicles = useMemo(() => vehicles.filter((v) => v?.status !== 'offline'), [vehicles]);

  useEffect(() => {
    fetchMissions();
  }, [fetchMissions]);

  const effectiveSelectedId = useMemo(() => {
    if (!activeVehicles.length) return '';
    const stillExists = selectedId && activeVehicles.some((v) => v.id === selectedId);
    return stillExists ? selectedId : activeVehicles[0].id;
  }, [activeVehicles, selectedId]);

  const activeMission = effectiveSelectedId ? getActiveMissionForVehicle(effectiveSelectedId) : null;

  // Tracks the GPS position where TAKEOFF was initiated (per vehicle).
  // Used to implement: 1st TAKEOFF => climb to ~1m, 2nd TAKEOFF => return to takeoff point.
  const takeoffOriginRef = useRef({});

  useMissionStream(effectiveSelectedId);

  const vehicle = activeVehicles.find((v) => v.id === effectiveSelectedId);
  const t = telemetry[effectiveSelectedId] || {};
  const isConnected = connectionStatus[effectiveSelectedId] === 'connected';
  const disabledReason = isConnected ? undefined : 'Vehicle not connected';
  const modeLabel = t.mode || vehicle?.mode || 'Unknown';
  const armedLabel = vehicle?.armed ? 'ARMED' : 'DISARMED';

  const handleSend = async (cmd) => {
    if (!effectiveSelectedId) return;

    const toastSuccess = (message) =>
      addToast({ type: 'success', title: 'Command Sent', message });

    const toastError = (err) => {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        'Command failed — check vehicle connection and try again.';
      addToast({ type: 'error', title: 'Command Failed', message: String(detail) });
    };

    try {
      if (cmd === COMMANDS.TAKEOFF) {
        const existingOrigin = takeoffOriginRef.current[effectiveSelectedId];
        const isArmed = Boolean(vehicle?.armed ?? t?.armed);

        // If already airborne/armed and we have an origin, treat TAKEOFF as "return to takeoff point".
        if (existingOrigin && isArmed) {
          await sendCommand(effectiveSelectedId, {
            command: COMMANDS.GOTO,
            params: {
              lat: existingOrigin.lat,
              lng: existingOrigin.lng,
              // Keep current altitude (safer across autopilots/altitude frames).
              alt: -1,
            },
          });
          toastSuccess(`RETURN TO TAKEOFF POINT sent to ${vehicle?.name || 'vehicle'}`);
          return;
        }

        // First TAKEOFF: record origin if we have a valid GPS fix.
        const lat = Number(t?.lat ?? t?.gps?.lat);
        const lng = Number(t?.lng ?? t?.gps?.lng);
        if (Number.isFinite(lat) && Number.isFinite(lng)) {
          takeoffOriginRef.current[effectiveSelectedId] = { lat, lng };
        }

        await sendCommand(effectiveSelectedId, { command: cmd, params: { altitude: 1.0 } });
        toastSuccess(`${String(cmd).replace(/_/g, ' ').toUpperCase()} sent to ${vehicle?.name || 'vehicle'}`);
        return;
      }

      await sendCommand(effectiveSelectedId, { command: cmd });
      toastSuccess(`${String(cmd).replace(/_/g, ' ').toUpperCase()} sent to ${vehicle?.name || 'vehicle'}`);
    } catch (err) {
      toastError(err);
      throw err; // re-throw so ActionButton's audit trail records the failure
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Control Panel</h1>
        <p className="text-sm text-slate-400 mt-1">Direct vehicle command and mode control</p>
      </div>

      {/* Vehicle Selector */}
      <Card>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {activeVehicles.map((v) => (
              <button key={v.id} onClick={() => setSelectedId(v.id)}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-all ${
                  effectiveSelectedId === v.id ? 'bg-blue-600/20 border-blue-500/30 text-blue-400' : 'bg-slate-800 border-slate-700 text-slate-400 hover:bg-slate-700'
                }`}>
                <StatusIndicator status={v.status} size="sm" />
                <span>{v.name}</span>
                <Badge status={v.status} className="text-[9px]" />
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {vehicle ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Commands */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle subtitle={`${vehicle.name} (${vehicle.callsign})`}>Vehicle Commands</CardTitle>
            </CardHeader>
            <CardContent>
              {/* Status Banner */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-6">
                <div className="p-3 rounded-lg border border-slate-700 bg-slate-800/60">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">Link</p>
                  <p className={`text-sm font-semibold ${isConnected ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {isConnected ? 'Connected' : 'Degraded'}
                  </p>
                </div>
                <div className="p-3 rounded-lg border border-slate-700 bg-slate-800/60">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">Arming</p>
                  <p className={`text-sm font-semibold ${vehicle.armed ? 'text-red-400' : 'text-slate-200'}`}>
                    {armedLabel}
                  </p>
                </div>
                <div className="p-3 rounded-lg border border-slate-700 bg-slate-800/60">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">Mode</p>
                  <p className="text-sm font-semibold text-slate-100">{modeLabel}</p>
                </div>
                <div className="p-3 rounded-lg border border-slate-700 bg-slate-800/60">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">Authority</p>
                  <p className="text-sm font-semibold text-slate-200">Cloud Supervisory</p>
                </div>
              </div>

              {/* Safety Commands */}
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-xs uppercase tracking-wider text-slate-500">Safety Controls</h4>
                <span className="text-[11px] text-slate-500">Shift+Click for Action Details</span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 mb-6">
                {vehicle?.armed ? (
                  <ControlActionButton
                    actionId="control.command.disarm"
                    icon={ShieldOff}
                    label="DISARM"
                    disabled={!isConnected}
                    disabledReason={disabledReason}
                    onAction={() => handleSend(COMMANDS.DISARM)}
                  />
                ) : (
                  <ControlActionButton
                    actionId="control.command.arm"
                    icon={ShieldCheck}
                    label="ARM"
                    disabled={!isConnected}
                    disabledReason={disabledReason}
                    onAction={() => handleSend(COMMANDS.ARM)}
                  />
                )}
                <ControlActionButton
                  actionId="control.command.takeoff"
                  icon={Plane}
                  label="TAKEOFF"
                  disabled={!isConnected}
                  disabledReason={disabledReason}
                  onAction={() => handleSend(COMMANDS.TAKEOFF)}
                />
                <ControlActionButton
                  actionId="control.command.land"
                  icon={ArrowDownToLine}
                  label="LAND"
                  disabled={!isConnected}
                  disabledReason={disabledReason}
                  onAction={() => handleSend(COMMANDS.LAND)}
                />
                <ControlActionButton
                  actionId="control.command.hold"
                  icon={Gauge}
                  label="HOLD"
                  disabled={!isConnected}
                  disabledReason={disabledReason}
                  onAction={() => handleSend(COMMANDS.HOLD)}
                />
              </div>

              {/* Emergency Controls */}
              <div className="border border-red-500/30 bg-red-500/5 rounded-xl p-4 mb-6">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h4 className="text-xs uppercase tracking-wider text-red-300">Emergency Controls</h4>
                    <p className="text-[11px] text-red-300/70">Use only to prevent harm or recover vehicle.</p>
                  </div>
                  <AlertTriangle className="w-5 h-5 text-red-400" />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <ActionButton
                    actionId="control.command.rtl"
                    icon={RotateCcw}
                    size="md"
                    disabled={!isConnected}
                    disabledReason={disabledReason}
                    onAction={() => handleSend(COMMANDS.RTL)}
                    className="justify-center"
                  >
                    Return To Launch
                  </ActionButton>
                  <ActionButton
                    actionId="control.command.emergency_stop"
                    icon={OctagonX}
                    size="md"
                    disabled={!isConnected}
                    disabledReason={disabledReason}
                    onAction={() => handleSend(COMMANDS.EMERGENCY_STOP)}
                    className="justify-center"
                  >
                    Emergency Stop
                  </ActionButton>
                </div>
              </div>

              {/* Flight Modes */}
              <h4 className="text-xs uppercase tracking-wider text-slate-500 mb-3">Flight Mode (State Transitions)</h4>
              <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-7 gap-2">
                {Object.entries(FLIGHT_MODES).map(([key, mode]) => (
                  <button key={key} disabled={!isConnected}
                    className={`p-2 rounded-lg border text-xs font-medium transition-all ${
                      t.mode === mode.label ? 'border-blue-500 bg-blue-600/20 text-blue-400' : 'border-slate-700 bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-40'
                    }`}>
                    {mode.label}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Live Status Panel */}
          <Card>
            <CardHeader><CardTitle>Live Status</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between p-2 bg-slate-700/30 rounded-lg">
                <span className="text-xs text-slate-500">Connection</span>
                <StatusIndicator status={isConnected ? 'connected' : 'disconnected'} showLabel />
              </div>
              <div className="flex items-center justify-between p-2 bg-slate-700/30 rounded-lg">
                <span className="text-xs text-slate-500">Armed</span>
                <Badge status={vehicle.armed ? 'armed' : 'disarmed'} dot />
              </div>
              <div className="flex items-center justify-between p-2 bg-slate-700/30 rounded-lg">
                <span className="text-xs text-slate-500">Mode</span>
                <span className="text-sm font-medium text-slate-200">{t.mode || vehicle.mode}</span>
              </div>
              <div className="flex items-center justify-between p-2 bg-slate-700/30 rounded-lg">
                <span className="text-xs text-slate-500">Mission</span>
                <span className="text-sm font-medium text-slate-200">{activeMission?.name || 'None'}</span>
              </div>
              {activeMission && (
                <div className="flex items-center justify-between p-2 bg-slate-700/30 rounded-lg">
                  <span className="text-xs text-slate-500">Mission State</span>
                  <span className="text-sm font-medium text-slate-200">{activeMission.status}</span>
                </div>
              )}
              {[
                ['Battery', `${Math.round(t.battery ?? 0)}%`],
                ['Altitude', `${(t.altitude ?? 0).toFixed(1)} m`],
                ['Speed', `${(t.groundspeed ?? 0).toFixed(1)} m/s`],
                ['Heading', `${Math.round(t.heading ?? 0)}°`],
                ['Satellites', t.satellites ?? 0],
                ['Voltage', `${(t.voltage ?? 0).toFixed(1)} V`],
              ].map(([label, val]) => (
                <div key={label} className="flex items-center justify-between p-2 bg-slate-700/30 rounded-lg">
                  <span className="text-xs text-slate-500">{label}</span>
                  <span className="text-sm font-mono text-slate-200">{val}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      ) : (
        <Card className="text-center py-16">
          <Gamepad2 className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">Select an active vehicle to control</p>
        </Card>
      )}
    </div>
  );
}


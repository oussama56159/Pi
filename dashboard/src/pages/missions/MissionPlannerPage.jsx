import { useEffect, useMemo, useState } from 'react';
import {
  Plus,
  Trash2,
  GripVertical,
  Upload,
  Download,
  Save,
  RotateCcw,
  Copy,
  Pencil,
  Link2,
  Unlink,
  Play,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';
import { MapContainer, TileLayer, Marker, Polyline, Polygon, Popup, useMapEvent } from 'react-leaflet';
import L from 'leaflet';
import Card, { CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import ActionButton from '@/components/actions/ActionButton';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';
import Input, { Select } from '@/components/ui/Input';
import Modal from '@/components/ui/Modal';
import { useMissionStore } from '@/stores/missionStore';
import { useFleetStore } from '@/stores/fleetStore';
import { useTelemetryStore } from '@/stores/telemetryStore';
import { useAuthStore } from '@/stores/authStore';
import { missionAPI } from '@/lib/api/endpoints';
import { MAP_CONFIG, ROLES } from '@/config/constants';
import { useMissionStream } from '@/lib/websocket/useMissionStream';
import {
  computeMissionDistanceMeters,
  estimateBatteryThresholdPercent,
  generateGridWaypoints,
  validateMissionAgainstGeofence,
} from '@/lib/missionPlanning';
import 'leaflet/dist/leaflet.css';

const DRONE_STATUS_LABELS = {
  idle: 'Idle',
  armed: 'Armed',
  in_mission: 'In Mission',
  warning: 'Warning',
  critical: 'Critical',
  offline: 'Offline',
};

const DRONE_STATUS_COLORS = {
  idle: '#22c55e',
  armed: '#3b82f6',
  in_mission: '#06b6d4',
  warning: '#f59e0b',
  critical: '#ef4444',
  offline: '#64748b',
};

const DEFAULT_GRID_PARAMS = {
  lineSpacing: 20,
  headingAngle: 0,
  overlapPercent: 25,
  edgeMargin: 5,
  turnaround: 'inside_only',
  altitude: 100,
};

const WAYPOINT_ACTIONS = [
  { value: 'NAV_WAYPOINT', label: 'Waypoint', hint: 'Navigate to this point' },
  { value: 'NAV_LOITER_TIME', label: 'Loiter / dwell', hint: 'Hold position for a time' },
  { value: 'NAV_TAKEOFF', label: 'Takeoff', hint: 'Climb and continue' },
  { value: 'NAV_LAND', label: 'Land', hint: 'Land at this point' },
  { value: 'NAV_RETURN_TO_LAUNCH', label: 'RTL', hint: 'Return to launch' },
  { value: 'DO_SET_CAM_TRIGG_DIST', label: 'Take photo / camera trigger', hint: 'Trigger the camera near this point' },
];

function toFiniteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function formatDegrees(value) {
  return `${Math.round((toFiniteNumber(value, 0) % 360 + 360) % 360)}°`;
}

function formatSeconds(value) {
  const seconds = Math.max(0, Math.round(toFiniteNumber(value, 0)));
  return `${seconds}s`;
}

function waypointActionLabel(command) {
  return WAYPOINT_ACTIONS.find((action) => action.value === command)?.label || command || 'Waypoint';
}

function computeBearingDegrees(from, to) {
  const lat1 = (toFiniteNumber(from?.lat) * Math.PI) / 180;
  const lat2 = (toFiniteNumber(to?.lat) * Math.PI) / 180;
  const deltaLng = ((toFiniteNumber(to?.lng) - toFiniteNumber(from?.lng)) * Math.PI) / 180;
  const y = Math.sin(deltaLng) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(deltaLng);
  const bearing = (Math.atan2(y, x) * 180) / Math.PI;
  return (bearing + 360) % 360;
}

function waypointSummary(wp) {
  const pieces = [waypointActionLabel(wp.command)];
  const dwell = toFiniteNumber(wp.param1, 0);
  const targetSeq = Math.round(toFiniteNumber(wp.param2, 0));
  const heading = toFiniteNumber(wp.param4, 0);

  if (dwell > 0) {
    pieces.push(`Stay ${formatSeconds(dwell)}`);
  }

  if (targetSeq > 0) {
    pieces.push(`Look at WP ${targetSeq}`);
  }

  if (Number.isFinite(heading)) {
    pieces.push(`Heading ${formatDegrees(heading)}`);
  }

  return pieces.join(' · ');
}

function normalizeGeofencePoints(source) {
  if (!Array.isArray(source)) return [];

  return source
    .map((point) => {
      if (Array.isArray(point) && point.length >= 2) {
        const first = Number(point[0]);
        const second = Number(point[1]);
        if (!Number.isFinite(first) || !Number.isFinite(second)) {
          return { lat: Number.NaN, lng: Number.NaN };
        }

        // Most of the app uses [lat, lng]. If a pair looks like [lng, lat], flip it.
        if (Math.abs(first) > 90 && Math.abs(second) <= 90) {
          return { lat: second, lng: first };
        }
        return { lat: first, lng: second };
      }

      const lat = Number(point?.lat ?? point?.latitude);
      const lng = Number(point?.lng ?? point?.lon ?? point?.longitude);
      return { lat, lng };
    })
    .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lng));
}

function createWaypointIcon(index, { selected = false } = {}) {
  return L.divIcon({
    className: 'aero-waypoint-icon',
    html: `<div style="width:26px;height:26px;border-radius:9999px;background:#3b82f6;border:2px solid ${selected ? '#22c55e' : 'rgba(15,23,42,0.9)'};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;">${index + 1}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
}

function resolveRotorCount(vehicleType) {
  switch (vehicleType) {
    case 'hexacopter':
      return 6;
    case 'octocopter':
      return 8;
    case 'quadcopter':
    default:
      return 4;
  }
}

function getRotorPoints(rotorCount) {
  if (rotorCount === 4) {
    return [
      { x: 14, y: 14 },
      { x: 50, y: 14 },
      { x: 14, y: 50 },
      { x: 50, y: 50 },
    ];
  }

  const cx = 32;
  const cy = 32;
  const radius = 22;
  const startAngleDeg = -90;
  return Array.from({ length: rotorCount }, (_, i) => {
    const angle = ((startAngleDeg + (i * 360) / rotorCount) * Math.PI) / 180;
    const x = cx + radius * Math.cos(angle);
    const y = cy + radius * Math.sin(angle);
    return { x: x.toFixed(1), y: y.toFixed(1) };
  });
}

function createRoverSvg(color) {
  return `
    <svg width="28" height="28" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <rect x="14" y="30" width="36" height="14" rx="4" fill="${color}" stroke="rgba(15,23,42,0.9)" stroke-width="4" />
      <rect x="16" y="24" width="22" height="10" rx="3" fill="${color}" stroke="rgba(255,255,255,0.95)" stroke-width="2" />
      <line x1="20" y1="28" x2="34" y2="28" stroke="rgba(255,255,255,0.95)" stroke-width="2" stroke-linecap="round" />
      <circle cx="22" cy="46" r="6" fill="${color}" stroke="rgba(255,255,255,0.95)" stroke-width="2" />
      <circle cx="42" cy="46" r="6" fill="${color}" stroke="rgba(255,255,255,0.95)" stroke-width="2" />
      <circle cx="22" cy="46" r="2" fill="rgba(255,255,255,0.95)" />
      <circle cx="42" cy="46" r="2" fill="rgba(255,255,255,0.95)" />
      <path d="M32 18 L27 28 L37 28 Z" fill="rgba(255,255,255,0.95)" />
    </svg>
  `;
}

function createDroneIcon(heading = 0, status = 'idle', vehicleType = 'quadcopter') {
  const color = DRONE_STATUS_COLORS[status] || DRONE_STATUS_COLORS.idle;
  if (vehicleType === 'rover') {
    return L.divIcon({
      className: 'aero-drone-icon',
      html: `
        <div style="transform:rotate(${heading}deg);width:28px;height:28px;display:flex;align-items:center;justify-content:center;">
          ${createRoverSvg(color)}
        </div>
      `,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
  }
  const rotorCount = resolveRotorCount(vehicleType);
  const points = getRotorPoints(rotorCount);
  const armsSvg = points
    .map(
      (p) =>
        `<line x1="32" y1="32" x2="${p.x}" y2="${p.y}" stroke="rgba(255,255,255,0.95)" stroke-width="3" stroke-linecap="round" />`
    )
    .join('');
  const rotorsSvg = points
    .map(
      (p) =>
        `<circle cx="${p.x}" cy="${p.y}" r="7" fill="${color}" stroke="rgba(255,255,255,0.95)" stroke-width="2" />`
    )
    .join('');
  return L.divIcon({
    className: 'aero-drone-icon',
    html: `
      <div style="transform:rotate(${heading}deg);width:28px;height:28px;display:flex;align-items:center;justify-content:center;">
        <svg width="28" height="28" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          ${armsSvg}
          ${rotorsSvg}

          <circle cx="32" cy="32" r="9" fill="${color}" stroke="rgba(15,23,42,0.9)" stroke-width="4" />
          <circle cx="32" cy="32" r="9" fill="none" stroke="rgba(255,255,255,0.95)" stroke-width="2" />

          <path d="M32 18 L27 28 L37 28 Z" fill="rgba(255,255,255,0.95)" />
        </svg>
      </div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

function MapClickHandler({ drawingGeofence, addWaypointsOnClick, onAddWaypoint, onAddGeofencePoint }) {
  useMapEvent('click', (e) => {
    if (drawingGeofence) {
      onAddGeofencePoint({ lat: e.latlng.lat, lng: e.latlng.lng });
      return;
    }

    // Reduce accidental waypoint creation: only add on explicit mode,
    // or allow Shift+Click as a lightweight shortcut.
    const shift = Boolean(e?.originalEvent?.shiftKey);
    if (addWaypointsOnClick || shift) {
      onAddWaypoint({ lat: e.latlng.lat, lng: e.latlng.lng });
    }
  });
  return null;
}

function getDroneStatus(vehicle, telemetry, connectionState) {
  const conn = connectionState || 'disconnected';
  const battery = Number(telemetry?.battery ?? vehicle?.battery_level ?? 0);
  const link = Number(telemetry?.link_quality ?? telemetry?.linkQuality ?? 0);

  if (vehicle?.status === 'offline' || conn === 'disconnected') return 'offline';
  if (vehicle?.status === 'critical' || battery < 15 || link < 25) return 'critical';
  if (vehicle?.status === 'warning' || battery < 25 || link < 45) return 'warning';
  if (vehicle?.status === 'in_mission' || telemetry?.mission_active) return 'in_mission';
  if (vehicle?.status === 'armed' || telemetry?.armed) return 'armed';
  return 'idle';
}

function WaypointRow({ wp, index, onUpdate, onRemove }) {
  const [latText, setLatText] = useState(() => (wp.lat === null || wp.lat === undefined ? '' : String(wp.lat)));
  const [lngText, setLngText] = useState(() => (wp.lng === null || wp.lng === undefined ? '' : String(wp.lng)));
  const [altText, setAltText] = useState(() => (wp.alt === null || wp.alt === undefined ? '' : String(wp.alt)));

  const commitNumber = (raw, fallback) => {
    if (raw === '') return fallback;
    const num = Number(raw);
    if (!Number.isFinite(num)) return fallback;
    return num;
  };

  return (
    <div className="flex items-center gap-2 p-2 bg-slate-700/30 rounded-lg group">
      <GripVertical className="w-4 h-4 text-slate-600 cursor-grab" />
      <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center text-xs font-bold text-white">{index + 1}</div>
      <div className="flex-1 grid grid-cols-4 gap-2">
        <input
          type="number"
          step="0.000001"
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
          placeholder="Lat"
          value={latText}
          onChange={(e) => setLatText(e.target.value)}
          onBlur={() => onUpdate(wp.id, { lat: commitNumber(latText, wp.lat) })}
        />
        <input
          type="number"
          step="0.000001"
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
          placeholder="Lng"
          value={lngText}
          onChange={(e) => setLngText(e.target.value)}
          onBlur={() => onUpdate(wp.id, { lng: commitNumber(lngText, wp.lng) })}
        />
        <input
          type="number"
          step="1"
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
          placeholder="Alt"
          value={altText}
          onChange={(e) => setAltText(e.target.value)}
          onBlur={() => onUpdate(wp.id, { alt: commitNumber(altText, wp.alt) })}
        />
        <select
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300"
          value={wp.altitude_mode || 'relative'}
          onChange={(e) => onUpdate(wp.id, { altitude_mode: e.target.value })}
        >
          <option value="relative">Relative</option>
          <option value="terrain">Terrain-follow (AGL)</option>
        </select>
      </div>
      <select
        className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300"
        value={wp.command || 'NAV_WAYPOINT'}
        onChange={(e) => onUpdate(wp.id, { command: e.target.value })}
      >
        <option value="NAV_WAYPOINT">Waypoint</option>
        <option value="NAV_LOITER_TIME">Loiter</option>
        <option value="NAV_RETURN_TO_LAUNCH">RTL</option>
        <option value="NAV_LAND">Land</option>
        <option value="NAV_TAKEOFF">Takeoff</option>
        <option value="DO_SET_CAM_TRIGG_DIST">Camera Trigger</option>
      </select>
      <button
        onClick={() => onRemove(wp.id)}
        title="Remove waypoint"
        className="p-1 text-slate-500 hover:text-red-400 transition-colors"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
}

function WaypointListItem({ wp, index, selected, onSelect, onRemove }) {
  return (
    <div
      className={`flex items-center justify-between gap-2 rounded-lg border p-2 text-left transition-colors ${
        selected
          ? 'border-blue-500/40 bg-blue-600/10'
          : 'border-slate-700 bg-slate-800/40 hover:bg-slate-700/30'
      }`}
    >
      <button type="button" onClick={onSelect} className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs font-semibold text-slate-200 truncate">WP {index + 1}</div>
          <div className="text-[11px] text-slate-500 truncate">{wp.command || 'NAV_WAYPOINT'}</div>
        </div>
        <div className="mt-0.5 flex items-center justify-between gap-2 text-[11px] text-slate-500">
          <span className="truncate">{Number(wp.lat).toFixed(5)}, {Number(wp.lng).toFixed(5)}</span>
          <span className="shrink-0">{Math.round(Number(wp.alt) || 0)}m · {(wp.altitude_mode || 'relative') === 'terrain' ? 'Terrain' : 'Relative'}</span>
        </div>
        <div className="mt-1 text-[11px] text-slate-400 truncate">{waypointSummary(wp)}</div>
      </button>
      <button
        type="button"
        onClick={onRemove}
        title="Remove waypoint"
        className="p-1 text-slate-500 hover:text-red-400 transition-colors"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
}

function SelectedWaypointEditor({ wp, index, allWaypoints, onUpdate, onRemove }) {
  const [latText, setLatText] = useState(() => (wp?.lat === null || wp?.lat === undefined ? '' : String(wp.lat)));
  const [lngText, setLngText] = useState(() => (wp?.lng === null || wp?.lng === undefined ? '' : String(wp.lng)));
  const [altText, setAltText] = useState(() => (wp?.alt === null || wp?.alt === undefined ? '' : String(wp.alt)));
  const [dwellText, setDwellText] = useState(() => (wp?.param1 === null || wp?.param1 === undefined ? '' : String(wp.param1)));
  const [targetSeqText, setTargetSeqText] = useState(() => (wp?.param2 === null || wp?.param2 === undefined ? '' : String(wp.param2)));
  const [headingText, setHeadingText] = useState(() => (wp?.param4 === null || wp?.param4 === undefined ? '' : String(wp.param4)));

  useEffect(() => {
    setLatText(wp?.lat === null || wp?.lat === undefined ? '' : String(wp.lat));
    setLngText(wp?.lng === null || wp?.lng === undefined ? '' : String(wp.lng));
    setAltText(wp?.alt === null || wp?.alt === undefined ? '' : String(wp.alt));
    setDwellText(wp?.param1 === null || wp?.param1 === undefined ? '' : String(wp.param1));
    setTargetSeqText(wp?.param2 === null || wp?.param2 === undefined ? '' : String(wp.param2));
    setHeadingText(wp?.param4 === null || wp?.param4 === undefined ? '' : String(wp.param4));
  }, [wp?.alt, wp?.id, wp?.lat, wp?.lng, wp?.param1, wp?.param2, wp?.param4]);

  const commitNumber = (raw, fallback) => {
    if (raw === '') return fallback;
    const num = Number(raw);
    if (!Number.isFinite(num)) return fallback;
    return num;
  };

  const targetOptions = [
    { value: '0', label: 'No target' },
    ...allWaypoints
      .filter((candidate) => candidate.id !== wp?.id)
      .map((candidate) => ({
        value: String(candidate.seq + 1),
        label: `WP ${candidate.seq + 1}`,
      })),
  ];

  useEffect(() => {
    if (!wp || !targetSeqText) return;

    const targetSeq = Number(targetSeqText);
    if (!Number.isFinite(targetSeq) || targetSeq <= 0) return;

    const targetWaypoint = allWaypoints.find((candidate) => candidate.seq + 1 === targetSeq);
    if (!targetWaypoint) return;

    const bearing = Math.round(computeBearingDegrees(wp, targetWaypoint) * 10) / 10;
    if (toFiniteNumber(headingText, null) !== bearing) {
      setHeadingText(String(bearing));
    }
    if (toFiniteNumber(wp.param4, null) !== bearing) {
      onUpdate(wp.id, { param4: bearing });
    }
  }, [allWaypoints, headingText, onUpdate, targetSeqText, wp]);

  const applyTargetSelection = (rawValue) => {
    const targetSeq = Number(rawValue) || 0;
    setTargetSeqText(targetSeq ? String(targetSeq) : '');

    if (!targetSeq || !wp) {
      onUpdate(wp.id, { param2: 0 });
      return;
    }

    const targetWaypoint = allWaypoints.find((candidate) => candidate.seq + 1 === targetSeq);
    const heading = targetWaypoint ? computeBearingDegrees(wp, targetWaypoint) : commitNumber(headingText, wp.param4);
    setHeadingText(String(heading));
    onUpdate(wp.id, { param2: targetSeq, param4: heading });
  };

  if (!wp) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-800/30 p-3 text-sm text-slate-500">
        Select a waypoint to edit its details.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/30 p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-slate-200">Selected: WP {index + 1}</div>
        <button
          type="button"
          onClick={() => onRemove(wp.id)}
          className="text-xs text-slate-500 hover:text-red-400 transition-colors"
        >
          Remove
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div>
          <label className="block text-[11px] text-slate-500 mb-1">Latitude</label>
          <input
            type="number"
            step="0.000001"
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
            value={latText}
            onChange={(e) => setLatText(e.target.value)}
            onBlur={() => onUpdate(wp.id, { lat: commitNumber(latText, wp.lat) })}
          />
        </div>
        <div>
          <label className="block text-[11px] text-slate-500 mb-1">Longitude</label>
          <input
            type="number"
            step="0.000001"
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
            value={lngText}
            onChange={(e) => setLngText(e.target.value)}
            onBlur={() => onUpdate(wp.id, { lng: commitNumber(lngText, wp.lng) })}
          />
        </div>
        <div>
          <label className="block text-[11px] text-slate-500 mb-1">Altitude (m)</label>
          <input
            type="number"
            step="1"
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
            value={altText}
            onChange={(e) => setAltText(e.target.value)}
            onBlur={() => onUpdate(wp.id, { alt: commitNumber(altText, wp.alt) })}
          />
        </div>
        <div>
          <label className="block text-[11px] text-slate-500 mb-1">Altitude Mode</label>
          <select
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-300"
            value={wp.altitude_mode || 'relative'}
            onChange={(e) => onUpdate(wp.id, { altitude_mode: e.target.value })}
          >
            <option value="relative">Relative</option>
            <option value="terrain">Terrain-follow (AGL)</option>
          </select>
        </div>
      </div>

      <div>
        <label className="block text-[11px] text-slate-500 mb-1">Action</label>
        <select
          className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-300"
          value={wp.command || 'NAV_WAYPOINT'}
          onChange={(e) => {
            const nextCommand = e.target.value;
            const nextUpdates = { command: nextCommand };
            if (nextCommand === 'NAV_LOITER_TIME' && toFiniteNumber(wp.param1, 0) <= 0) {
              nextUpdates.param1 = 5;
            }
            if (nextCommand === 'DO_SET_CAM_TRIGG_DIST' && toFiniteNumber(wp.param1, 0) <= 0) {
              nextUpdates.param1 = 1;
            }
            onUpdate(wp.id, nextUpdates);
          }}
        >
          {WAYPOINT_ACTIONS.map((action) => (
            <option key={action.value} value={action.value}>{action.label}</option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div>
          <label className="block text-[11px] text-slate-500 mb-1">Stay time (seconds)</label>
          <input
            type="number"
            min="0"
            step="1"
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
            value={dwellText}
            onChange={(e) => setDwellText(e.target.value)}
            onBlur={() => onUpdate(wp.id, { param1: commitNumber(dwellText, wp.param1) })}
          />
          <p className="mt-1 text-[11px] text-slate-500">Used as waypoint hold time or loiter duration, depending on the selected action.</p>
        </div>

        <div>
          <label className="block text-[11px] text-slate-500 mb-1">Heading (degrees)</label>
          <input
            type="number"
            step="1"
            min="0"
            max="359"
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
            value={headingText}
            onChange={(e) => setHeadingText(e.target.value)}
            onBlur={() => onUpdate(wp.id, { param4: commitNumber(headingText, wp.param4) })}
          />
        </div>

        <div className="md:col-span-2">
          <label className="block text-[11px] text-slate-500 mb-1">Look at waypoint</label>
          <select
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-300"
            value={targetSeqText ? String(targetSeqText) : '0'}
            onChange={(e) => applyTargetSelection(e.target.value)}
          >
            {targetOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <p className="mt-1 text-[11px] text-slate-500">
            Picking another waypoint will auto-calculate heading toward that point.
          </p>
        </div>
      </div>
    </div>
  );
}

export default function MissionPlannerPage() {
  const missions = useMissionStore((s) => s.missions);
  const selectedMissionId = useMissionStore((s) => s.selectedMissionId);
  const activeMission = useMissionStore((s) => s.activeMission);
  const isLoading = useMissionStore((s) => s.isLoading);
  const fetchMissions = useMissionStore((s) => s.fetchMissions);
  const fetchMission = useMissionStore((s) => s.fetchMission);
  const createMission = useMissionStore((s) => s.createMission);
  const updateMission = useMissionStore((s) => s.updateMission);
  const deleteMission = useMissionStore((s) => s.deleteMission);
  const assignMission = useMissionStore((s) => s.assignMission);
  const unassignMission = useMissionStore((s) => s.unassignMission);
  const selectMission = useMissionStore((s) => s.selectMission);
  const waypoints = useMissionStore((s) => s.waypoints);
  const addWaypoint = useMissionStore((s) => s.addWaypoint);
  const updateWaypoint = useMissionStore((s) => s.updateWaypoint);
  const removeWaypoint = useMissionStore((s) => s.removeWaypoint);
  const clearWaypoints = useMissionStore((s) => s.clearWaypoints);

  const vehicles = useFleetStore((s) => s.vehicles);
  const fetchVehicles = useFleetStore((s) => s.fetchVehicles);
  const fleets = useFleetStore((s) => s.fleets);
  const fetchFleets = useFleetStore((s) => s.fetchFleets);

  const vehicleTelemetry = useTelemetryStore((s) => s.vehicleTelemetry);
  const connectionStatus = useTelemetryStore((s) => s.connectionStatus);
  const hasAnyRole = useAuthStore((s) => s.hasAnyRole);

  const [showNewMission, setShowNewMission] = useState(false);
  const [showEditMission, setShowEditMission] = useState(false);
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [editingMission, setEditingMission] = useState(null);
  const [assigningMission, setAssigningMission] = useState(null);

  const [missionName, setMissionName] = useState('');
  const [assignVehicleIds, setAssignVehicleIds] = useState([]);
  const [missionType, setMissionType] = useState('survey');
  const [searchQuery, setSearchQuery] = useState('');
  const [vehicleFilter, setVehicleFilter] = useState('');
  const [fleetFilter, setFleetFilter] = useState('');

  const [selectedFleetId, setSelectedFleetId] = useState('');
  const [launchPolicy, setLaunchPolicy] = useState('all_or_none');
  const [terrainFallbackPolicy, setTerrainFallbackPolicy] = useState('use_relative');

  const [isDrawingGeofence, setIsDrawingGeofence] = useState(false);
  const [geofencePoints, setGeofencePoints] = useState([]);
  const [geofenceBackup, setGeofenceBackup] = useState(null);

  const [addWaypointsOnClick, setAddWaypointsOnClick] = useState(false);

  const [gridParams, setGridParams] = useState(DEFAULT_GRID_PARAMS);
  const [gridPreviewWaypoints, setGridPreviewWaypoints] = useState([]);

  const [plannerStep, setPlannerStep] = useState('area');
  const [selectedWaypointId, setSelectedWaypointId] = useState(null);
  const [showInfoChecks, setShowInfoChecks] = useState(false);

  const [preflightResults, setPreflightResults] = useState([]);
  const [readinessSummary, setReadinessSummary] = useState({ ready: 0, total: 0, blockers: 0, warnings: 0 });
  const [missionStartError, setMissionStartError] = useState('');
  const [isStartingMission, setIsStartingMission] = useState(false);
  const [missionUploadError, setMissionUploadError] = useState('');
  const [isUploadingMission, setIsUploadingMission] = useState(false);
  const [missionDownloadError, setMissionDownloadError] = useState('');
  const [isDownloadingMission, setIsDownloadingMission] = useState(false);

  useEffect(() => {
    fetchMissions();
    fetchVehicles();
    fetchFleets();
  }, [fetchMissions, fetchVehicles, fetchFleets]);

  useEffect(() => {
    if (waypoints.length === 0) {
      if (selectedWaypointId !== null) setSelectedWaypointId(null);
      return;
    }

    if (!selectedWaypointId || !waypoints.some((wp) => wp.id === selectedWaypointId)) {
      setSelectedWaypointId(waypoints[0].id);
    }
  }, [waypoints, selectedWaypointId]);

  // Keep map click modes mutually exclusive.
  useEffect(() => {
    if (isDrawingGeofence) setAddWaypointsOnClick(false);
  }, [isDrawingGeofence]);

  const path = useMemo(() => waypoints.map((wp) => [wp.lat, wp.lng]), [waypoints]);

  const previewPath = useMemo(() => gridPreviewWaypoints.map((wp) => [wp.lat, wp.lng]), [gridPreviewWaypoints]);

  const selectedWaypoint = useMemo(
    () => (selectedWaypointId ? waypoints.find((wp) => wp.id === selectedWaypointId) : null),
    [waypoints, selectedWaypointId]
  );

  const selectedWaypointIndex = useMemo(() => {
    if (!selectedWaypointId) return -1;
    return waypoints.findIndex((wp) => wp.id === selectedWaypointId);
  }, [waypoints, selectedWaypointId]);

  const filteredMissions = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const vehicleMap = new Map(vehicles.map((v) => [v.id, v]));
    return missions.filter((m) => {
      const matchesQuery = !q || m.name?.toLowerCase().includes(q) || m.type?.toLowerCase().includes(q);
      const assigned = m.assigned_vehicle_ids || m.assignments?.filter((a) => a.active).map((a) => a.vehicle_id) || [];
      const matchesVehicle = !vehicleFilter || assigned.includes(vehicleFilter) || m.vehicle_id === vehicleFilter;
      const assignedFleetIds = assigned.map((id) => vehicleMap.get(id)?.fleet_id).filter(Boolean);
      const matchesFleet = !fleetFilter || assignedFleetIds.includes(fleetFilter);
      return matchesQuery && matchesVehicle && matchesFleet;
    });
  }, [missions, searchQuery, vehicleFilter, fleetFilter, vehicles]);

  const fleetVehicles = useMemo(() => {
    if (!selectedFleetId) return [];
    return vehicles.filter((v) => v.fleet_id === selectedFleetId);
  }, [vehicles, selectedFleetId]);

  const selectedMission = useMemo(() => missions.find((m) => m.id === selectedMissionId), [missions, selectedMissionId]);

  const assignedVehicleIds = useMemo(
    () => selectedMission?.assigned_vehicle_ids || selectedMission?.assignments?.filter((a) => a.active).map((a) => a.vehicle_id) || [],
    [selectedMission]
  );

  const launchVehicles = useMemo(() => {
    if (fleetVehicles.length) return fleetVehicles;
    return vehicles.filter((v) => assignedVehicleIds.includes(v.id));
  }, [fleetVehicles, vehicles, assignedVehicleIds]);

  const canPilotMission = hasAnyRole([ROLES.SUPER_ADMIN, ROLES.ADMIN, ROLES.PILOT]);
  const missionStreamVehicleId = useMemo(
    () => launchVehicles[0]?.id || assignedVehicleIds[0] || null,
    [launchVehicles, assignedVehicleIds]
  );
  useMissionStream(missionStreamVehicleId);

  const missionValidation = useMemo(() => validateMissionAgainstGeofence(waypoints, geofencePoints), [waypoints, geofencePoints]);

  const usesTerrainFollow = useMemo(() => waypoints.some((wp) => (wp.altitude_mode || 'relative') === 'terrain'), [waypoints]);

  const terrainAvailable = useMemo(() => {
    if (!usesTerrainFollow) return true;
    if (launchVehicles.length === 0) return false;
    return launchVehicles.every((v) => {
      const t = vehicleTelemetry[v.id] || {};
      return t.terrain_available === true || Number.isFinite(Number(t.terrain_altitude));
    });
  }, [usesTerrainFollow, launchVehicles, vehicleTelemetry]);

  const droneMarkers = useMemo(() => {
    return vehicles
      .map((v) => {
        const t = vehicleTelemetry[v.id] || {};
        const lat = Number(t.latitude ?? t.lat ?? v.latitude);
        const lng = Number(t.longitude ?? t.lng ?? v.longitude);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;

        const status = getDroneStatus(v, t, connectionStatus[v.id]);
        return {
          id: v.id,
          name: v.name,
          callsign: v.callsign,
          type: v.type,
          lat,
          lng,
          heading: Number(t.heading) || 0,
          battery: Number(t.battery ?? v.battery_level ?? 0),
          altitude: Number(t.altitude ?? 0),
          speed: Number(t.groundspeed ?? 0),
          gpsQuality: Number(t.gps_quality ?? t.satellites ?? 0),
          linkQuality: Number(t.link_quality ?? t.linkQuality ?? 0),
          status,
        };
      })
      .filter(Boolean);
  }, [vehicles, vehicleTelemetry, connectionStatus]);

  const openCreateModal = () => {
    setEditingMission(null);
    setMissionName('');
    setMissionType('survey');
    setShowNewMission(true);
  };

  const openEditModal = (mission) => {
    setEditingMission(mission);
    setMissionName(mission.name || '');
    setMissionType(mission.type || 'survey');
    setShowEditMission(true);
  };

  const openAssignModal = (mission) => {
    setAssigningMission(mission);
    const fallback = (mission.assignments || []).filter((a) => a.active).map((a) => a.vehicle_id);
    setAssignVehicleIds(mission.assigned_vehicle_ids || fallback);
    setShowAssignModal(true);
  };

  const openAssignForSelectedMission = () => {
    if (!selectedMission) {
      setMissionStartError('Load a mission first to assign it to drones or fleets.');
      return;
    }
    openAssignModal(selectedMission);
  };

  const buildPlannerStatePayload = (overrides = {}) => ({
    geofence_polygon: overrides.geofencePoints ?? geofencePoints,
    terrain_fallback_policy: overrides.terrainFallbackPolicy ?? terrainFallbackPolicy,
    launch_policy: overrides.launchPolicy ?? launchPolicy,
    grid_config: overrides.gridParams ?? gridParams,
  });

  const mergeSettingsWithPlannerState = (baseSettings, overrides) => {
    const safeBase = baseSettings && typeof baseSettings === 'object' ? baseSettings : {};
    const existingPlannerState =
      safeBase.planner_state && typeof safeBase.planner_state === 'object' ? safeBase.planner_state : {};

    return {
      ...safeBase,
      planner_state: {
        ...existingPlannerState,
        ...buildPlannerStatePayload(overrides),
      },
    };
  };

  const persistPlannerStateDraft = async (overrides) => {
    if (!selectedMissionId) return;
    const baseSettings =
      activeMission?.id === selectedMissionId
        ? activeMission.settings
        : selectedMission?.settings;
    await updateMission(selectedMissionId, {
      waypoints,
      settings: mergeSettingsWithPlannerState(baseSettings, overrides),
    });
  };

  const handleDeletePolygon = async () => {
    setGeofencePoints([]);
    setGridPreviewWaypoints([]);
    await persistPlannerStateDraft({ geofencePoints: [] });
  };

  const hydrateMissionPlanningState = (mission) => {
    const plannerState = mission?.settings?.planner_state || mission?.settings || {};
    const geofenceSource =
      plannerState.geofence_polygon ||
      plannerState.geofence ||
      plannerState.geofence_points ||
      plannerState.geofence_vertices ||
      mission?.geofence_polygon ||
      mission?.geofence ||
      [];
    setGeofencePoints(normalizeGeofencePoints(geofenceSource));
    setTerrainFallbackPolicy(plannerState.terrain_fallback_policy || 'use_relative');
    setLaunchPolicy(plannerState.launch_policy || 'all_or_none');
    setGridParams({ ...DEFAULT_GRID_PARAMS, ...(plannerState.grid_config || {}) });
    setGridPreviewWaypoints([]);
    setPreflightResults([]);
    setReadinessSummary({ ready: 0, total: 0, blockers: 0, warnings: 0 });
    setMissionStartError('');
  };

  const handleAssignMission = async () => {
    if (!assigningMission) return;
    if (assignVehicleIds.length === 0) {
      const fallback = (assigningMission.assignments || []).filter((a) => a.active).map((a) => a.vehicle_id);
      await unassignMission(assigningMission.id, assigningMission.assigned_vehicle_ids || fallback);
      setShowAssignModal(false);
      return;
    }
    await assignMission(assigningMission.id, assignVehicleIds, { replaceExisting: true });
    setShowAssignModal(false);
  };

  const buildMissionPayload = () => {
    const baseSettings = editingMission
      ? (activeMission?.id === editingMission.id ? activeMission.settings : editingMission.settings)
      : {};
    return {
      name: missionName.trim(),
      type: missionType,
      waypoints,
      settings: mergeSettingsWithPlannerState(baseSettings),
    };
  };

  const handleSaveMission = async () => {
    if (!missionName.trim()) return;
    const payload = buildMissionPayload();
    if (editingMission) {
      await updateMission(editingMission.id, payload);
      setShowEditMission(false);
    } else {
      const created = await createMission(payload);
      selectMission(created.id);
      setShowNewMission(false);
    }
  };

  const handleSaveDraft = async () => {
    await persistPlannerStateDraft();
  };

  const handleUploadMission = async () => {
    setMissionUploadError('');
    if (!selectedMissionId) {
      setMissionUploadError('Load a mission first to upload it to vehicles.');
      return;
    }
    if (launchVehicles.length === 0) {
      setMissionUploadError('No drones selected. Choose a fleet or assign drones to this mission.');
      return;
    }
    if (waypoints.length === 0) {
      setMissionUploadError('No waypoints to upload.');
      return;
    }

    setIsUploadingMission(true);
    try {
      const results = await Promise.allSettled(launchVehicles.map((v) => missionAPI.upload(v.id, selectedMissionId)));
      const failed = results.filter((r) => r.status === 'rejected').length;
      if (failed > 0) {
        setMissionUploadError(`${failed} mission upload(s) failed. Check edge agent connectivity and MQTT.`);
      }
      await fetchMissions();
      await fetchMission(selectedMissionId);
    } finally {
      setIsUploadingMission(false);
    }
  };

  const handleDownloadMission = async () => {
    setMissionDownloadError('');
    if (launchVehicles.length === 0) {
      setMissionDownloadError('No drone selected. Choose a fleet or assign a drone to download from.');
      return;
    }
    if (launchVehicles.length !== 1) {
      setMissionDownloadError('Select exactly one vehicle to download its mission.');
      return;
    }

    setIsDownloadingMission(true);
    try {
      const vehicle = launchVehicles[0];
      const { data } = await missionAPI.download(vehicle.id);
      await fetchMissions();
      selectMission(data.id);
      const mission = await fetchMission(data.id);
      hydrateMissionPlanningState(mission);
    } catch (err) {
      setMissionDownloadError(err?.response?.data?.detail || err?.message || 'Mission download failed');
    } finally {
      setIsDownloadingMission(false);
    }
  };

  const handleSelectMission = async (missionId) => {
    selectMission(missionId);
    const mission = await fetchMission(missionId);
    hydrateMissionPlanningState(mission);
  };

  const handleDeleteMission = async (missionId) => {
    await deleteMission(missionId);
    if (selectedMissionId === missionId) {
      selectMission(null);
      clearWaypoints();
      setGeofencePoints([]);
      setPreflightResults([]);
      setReadinessSummary({ ready: 0, total: 0, blockers: 0, warnings: 0 });
    }
  };

  const handleDuplicateMission = async (mission) => {
    const baseSettings = mission?.settings;
    const plannerState = baseSettings?.planner_state || baseSettings || {};
    const geofencePolygon = normalizeGeofencePoints(
      plannerState.geofence_polygon ||
      plannerState.geofence ||
      plannerState.geofence_points ||
      plannerState.geofence_vertices ||
      []
    );

    const payload = {
      name: `${mission.name} Copy`,
      type: mission.type || 'survey',
      waypoints: mission.waypoints || [],
      settings: mergeSettingsWithPlannerState(baseSettings, {
        geofencePoints: geofencePolygon.length ? geofencePolygon : geofencePoints,
        terrainFallbackPolicy: plannerState.terrain_fallback_policy || terrainFallbackPolicy,
        launchPolicy: plannerState.launch_policy || launchPolicy,
        gridParams: plannerState.grid_config || gridParams,
      }),
    };
    await createMission(payload);
  };

  const handleAddWaypoint = ({ lat, lng } = {}) => {
    const id = crypto.randomUUID();
    const waypoint = {
      id,
      lat: typeof lat === 'number' ? lat : 36.8065 + (Math.random() - 0.5) * 0.02,
      lng: typeof lng === 'number' ? lng : 10.1815 + (Math.random() - 0.5) * 0.02,
      alt: 100,
      altitude_mode: 'relative',
      command: 'NAV_WAYPOINT',
      param1: 0,
      param2: 0,
      param3: 0,
      param4: 0,
    };
    addWaypoint(waypoint);
    setSelectedWaypointId(id);
  };

  const handleGeofenceVertexDrag = (index, latlng) => {
    setGeofencePoints((prev) => prev.map((p, i) => (i === index ? { lat: latlng.lat, lng: latlng.lng } : p)));
  };

  const handleRemoveGeofenceVertex = (index) => {
    setGeofencePoints((prev) => prev.filter((_, i) => i !== index));
  };

  const beginGeofenceEdit = ({ clear = false } = {}) => {
    setGeofenceBackup(geofencePoints);
    if (clear) setGeofencePoints([]);
    setIsDrawingGeofence(true);
  };

  const cancelGeofenceEdit = () => {
    if (geofenceBackup) setGeofencePoints(geofenceBackup);
    setGeofenceBackup(null);
    setIsDrawingGeofence(false);
  };

  const finishGeofenceEdit = async () => {
    setGeofenceBackup(null);
    setIsDrawingGeofence(false);

    // Persist geofence updates so they load next time.
    await persistPlannerStateDraft();
  };

  const undoGeofencePoint = () => {
    setGeofencePoints((prev) => prev.slice(0, -1));
  };

  const handleGenerateGridPreview = () => {
    if (geofencePoints.length < 3) {
      setMissionStartError('Grid generation requires a geofence polygon with at least 3 vertices.');
      return;
    }
    const generated = generateGridWaypoints(geofencePoints, {
      ...gridParams,
      altitudeMode: usesTerrainFollow ? 'terrain' : 'relative',
    });
    setGridPreviewWaypoints(generated);
    setMissionStartError('');
  };

  const handleApplyGridPreview = () => {
    if (gridPreviewWaypoints.length === 0) return;
    clearWaypoints();
    const wps = gridPreviewWaypoints.map((wp) => ({ ...wp, id: crypto.randomUUID() }));
    wps.forEach((wp) => addWaypoint(wp));
    if (wps.length) setSelectedWaypointId(wps[0].id);
    setGridPreviewWaypoints([]);
  };

  const handleAssignFleet = async () => {
    if (!selectedMissionId || !selectedFleetId) return;
    const ids = fleetVehicles.map((v) => v.id);
    await assignMission(selectedMissionId, ids, { replaceExisting: true });
  };

  const buildPreflightForDrone = (vehicle) => {
    const telemetry = vehicleTelemetry[vehicle.id] || {};
    const conn = connectionStatus[vehicle.id] || 'disconnected';
    const checks = [];

    const addCheck = (name, level, message, hint) => {
      checks.push({ name, level, message, hint });
    };

    if (!missionValidation.valid) {
      addCheck('mission validity', 'BLOCKER', missionValidation.reasons[0], 'Adjust geofence/waypoints until path is fully inside polygon.');
    } else {
      addCheck('mission validity', 'INFO', 'Mission path is valid inside geofence.', 'No action needed.');
    }

    if (geofencePoints.length < 3) {
      addCheck('geofence', 'BLOCKER', 'Geofence polygon is not defined.', 'Draw and finish a polygon before start.');
    } else {
      addCheck('geofence', 'INFO', `Geofence ready (${geofencePoints.length} vertices).`, 'No action needed.');
    }

    const dronePosition = {
      lat: Number(telemetry.latitude ?? telemetry.lat ?? vehicle.latitude),
      lng: Number(telemetry.longitude ?? telemetry.lng ?? vehicle.longitude),
    };
    const missionDistanceM = computeMissionDistanceMeters(waypoints, dronePosition);
    const requiredBattery = estimateBatteryThresholdPercent(missionDistanceM);
    const batteryNow = Number(telemetry.battery ?? vehicle.battery_level ?? 0);

    if (batteryNow >= requiredBattery) {
      addCheck(
        'battery',
        'INFO',
        `Battery pass: current ${Math.round(batteryNow)}% / threshold ${requiredBattery}% (includes mission, RTL, reserve).`,
        'No action needed.'
      );
    } else {
      addCheck(
        'battery',
        'BLOCKER',
        `Battery fail: current ${Math.round(batteryNow)}% / threshold ${requiredBattery}% (includes mission, RTL, reserve).`,
        'Recharge battery or reduce mission distance/altitude.'
      );
    }

    const satellites = Number(telemetry.satellites ?? telemetry.gps_quality ?? 0);
    const ekfOk = telemetry.ekf_ok !== false;
    if (!ekfOk || satellites < 6) {
      addCheck('gps/ekf', 'BLOCKER', `GPS/EKF fail: satellites ${satellites}, EKF ${ekfOk ? 'ok' : 'not ok'}.`, 'Wait for better GPS lock and EKF stabilization.');
    } else if (satellites < 8) {
      addCheck('gps/ekf', 'WARNING', `GPS marginal: satellites ${satellites}, EKF ok.`, 'Prefer at least 8 satellites before launch.');
    } else {
      addCheck('gps/ekf', 'INFO', `GPS/EKF pass: satellites ${satellites}, EKF ok.`, 'No action needed.');
    }

    const link = Number(telemetry.link_quality ?? telemetry.linkQuality ?? 0);
    if (conn === 'disconnected' || vehicle.status === 'offline' || link < 30) {
      addCheck('comm link', 'BLOCKER', `Comm link fail: state ${conn}, link quality ${Math.round(link)}%.`, 'Restore telemetry link and verify RF/network connectivity.');
    } else if (link < 55) {
      addCheck('comm link', 'WARNING', `Comm link weak: quality ${Math.round(link)}%.`, 'Improve antenna position or reduce range before launch.');
    } else {
      addCheck('comm link', 'INFO', `Comm link pass: quality ${Math.round(link)}%.`, 'No action needed.');
    }

    const droneStatus = getDroneStatus(vehicle, telemetry, conn);
    if (droneStatus === 'critical' || droneStatus === 'offline') {
      addCheck('vehicle health', 'BLOCKER', `Vehicle health fail: state ${DRONE_STATUS_LABELS[droneStatus]}.`, 'Resolve critical/offline status before mission start.');
    } else if (droneStatus === 'warning') {
      addCheck('vehicle health', 'WARNING', 'Vehicle health warning detected.', 'Review onboard warnings and clear if possible.');
    } else {
      addCheck('vehicle health', 'INFO', `Vehicle health pass: state ${DRONE_STATUS_LABELS[droneStatus]}.`, 'No action needed.');
    }

    if (usesTerrainFollow && !terrainAvailable) {
      if (terrainFallbackPolicy === 'block_start') {
        addCheck('terrain data', 'BLOCKER', 'Terrain-follow requested but terrain data is unavailable.', 'Switch fallback to Relative or wait for terrain service availability.');
      } else {
        addCheck('terrain data', 'WARNING', 'Terrain-follow requested but terrain data is unavailable.', 'Fallback policy will use Relative altitude mode.');
      }
    } else if (usesTerrainFollow) {
      addCheck('terrain data', 'INFO', 'Terrain data available for terrain-follow mode.', 'No action needed.');
    }

    const blockers = checks.filter((c) => c.level === 'BLOCKER').length;
    const warnings = checks.filter((c) => c.level === 'WARNING').length;

    return {
      vehicleId: vehicle.id,
      vehicleName: vehicle.name,
      status: blockers ? 'blocked' : 'ready',
      blockers,
      warnings,
      checks,
    };
  };

  const runPreflightChecks = () => {
    const targets = launchVehicles;
    const results = targets.map((v) => buildPreflightForDrone(v));
    const summary = {
      ready: results.filter((r) => r.blockers === 0).length,
      total: results.length,
      blockers: results.reduce((sum, r) => sum + r.blockers, 0),
      warnings: results.reduce((sum, r) => sum + r.warnings, 0),
    };
    setPreflightResults(results);
    setReadinessSummary(summary);
    return { results, summary };
  };

  const handleStartFleetMission = async () => {
    setMissionStartError('');

    if (!selectedMissionId) {
      setMissionStartError('Select and load a mission before synchronized start.');
      return;
    }
    if (launchVehicles.length === 0) {
      setMissionStartError('No drones selected. Choose a fleet or assign drones to this mission.');
      return;
    }

    const { results, summary } = runPreflightChecks();

    if (!missionValidation.valid) {
      setMissionStartError(missionValidation.reasons[0]);
      return;
    }

    if (launchPolicy === 'all_or_none' && summary.ready < summary.total) {
      setMissionStartError('Launch blocked by policy all-or-none: one or more drones have BLOCKER checks.');
      return;
    }

    const readyVehicleIds = results.filter((r) => r.blockers === 0).map((r) => r.vehicleId);
    if (readyVehicleIds.length === 0) {
      setMissionStartError('Mission start blocked: every selected drone has at least one BLOCKER check.');
      return;
    }

    setIsStartingMission(true);
    try {
      const targets = launchPolicy === 'launch_ready_only' ? readyVehicleIds : launchVehicles.map((v) => v.id);
      const startResults = await Promise.allSettled(targets.map((vehicleId) => missionAPI.start(vehicleId, selectedMissionId)));
      const failed = startResults.filter((r) => r.status === 'rejected').length;
      if (failed > 0) {
        setMissionStartError(`${failed} mission start command(s) failed. Check command service and telemetry links.`);
      }
    } finally {
      setIsStartingMission(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Mission Planner</h1>
          <p className="text-sm text-slate-400 mt-1">Plan, validate, assign, and synchronize autonomous fleet missions</p>
        </div>
        <ActionButton actionId="mission.create" icon={Plus} onAction={openCreateModal}>
          New Mission
        </ActionButton>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle subtitle={`${missions.length} missions`}>Missions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <Input placeholder="Search missions" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
              <select
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300"
                value={vehicleFilter}
                onChange={(e) => setVehicleFilter(e.target.value)}
              >
                <option value="">All vehicles</option>
                {vehicles.map((v) => (
                  <option key={v.id} value={v.id}>{v.name} ({v.callsign})</option>
                ))}
              </select>
              <select
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300"
                value={fleetFilter}
                onChange={(e) => setFleetFilter(e.target.value)}
              >
                <option value="">All fleets</option>
                {fleets.map((f) => (
                  <option key={f.id} value={f.id}>{f.name}</option>
                ))}
              </select>
            </div>

            <div className="space-y-2 max-h-[820px] overflow-y-auto">
              {filteredMissions.map((m) => {
                const assignedIds = m.assigned_vehicle_ids || (m.assignments || []).filter((a) => a.active).map((a) => a.vehicle_id) || [];
                return (
                  <div
                    key={m.id}
                    className={`p-3 rounded-lg border transition-colors ${
                      selectedMissionId === m.id
                        ? 'bg-blue-600/10 border-blue-500/40'
                        : 'bg-slate-700/30 border-slate-700 hover:bg-slate-700/50'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium text-slate-200">{m.name}</p>
                        <p className="text-xs text-slate-500">{m.waypoints?.length || 0} waypoints • {m.type}</p>
                      </div>
                      <Badge color={m.status === 'in_progress' ? 'blue' : m.status === 'completed' ? 'green' : 'gray'}>{m.status}</Badge>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <ActionButton actionId="mission.load" size="xs" variant="secondary" onAction={() => handleSelectMission(m.id)}>
                        Load
                      </ActionButton>
                      <ActionButton actionId="mission.update" size="xs" variant="ghost" icon={Pencil} onAction={() => openEditModal(m)}>
                        Edit
                      </ActionButton>
                      <ActionButton actionId="mission.assign" size="xs" variant="ghost" icon={Link2} onAction={() => openAssignModal(m)}>
                        Assign
                      </ActionButton>
                      <ActionButton actionId="mission.duplicate" size="xs" variant="ghost" icon={Copy} onAction={() => handleDuplicateMission(m)}>
                        Duplicate
                      </ActionButton>
                      <ActionButton actionId="mission.delete" size="xs" variant="ghost" icon={Trash2} onAction={() => handleDeleteMission(m.id)}>
                        Delete
                      </ActionButton>
                    </div>
                    {!!assignedIds.length && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {assignedIds.slice(0, 3).map((id) => {
                          const v = vehicles.find((veh) => veh.id === id);
                          if (!v) return null;
                          return (
                            <span key={id} className="px-2 py-0.5 text-[10px] rounded-full bg-slate-700 text-slate-300">
                              {v.callsign || v.name}
                            </span>
                          );
                        })}
                        {assignedIds.length > 3 && (
                          <span className="px-2 py-0.5 text-[10px] rounded-full bg-slate-700 text-slate-400">
                            +{assignedIds.length - 3}
                          </span>
                        )}
                      </div>
                    )}
                    {m.status === 'in_progress' && (
                      <div className="mt-2 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                        <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${m.progress}%` }} />
                      </div>
                    )}
                  </div>
                );
              })}
              {filteredMissions.length === 0 && (
                <div className="p-6 text-center text-sm text-slate-500 border border-dashed border-slate-700 rounded-lg">
                  {isLoading ? 'Loading missions...' : 'No missions match your search.'}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader action={
            <div className="flex gap-2">
              <ActionButton actionId="mission.draft.clear" size="xs" variant="ghost" icon={RotateCcw} onAction={() => { clearWaypoints(); setGridPreviewWaypoints([]); }}>
                Clear
              </ActionButton>
              <ActionButton
                actionId="mission.draft.save"
                size="xs"
                variant="secondary"
                icon={Save}
                onAction={handleSaveDraft}
                disabled={!selectedMissionId}
                disabledReason="Load a mission first"
              >
                Save
              </ActionButton>
              <ActionButton
                actionId="mission.upload"
                size="xs"
                icon={Upload}
                loading={isUploadingMission}
                onAction={handleUploadMission}
                disabled={!canPilotMission || !selectedMissionId || waypoints.length === 0 || launchVehicles.length === 0 || isUploadingMission}
                disabledReason={
                  !canPilotMission
                    ? 'Pilot role required'
                    : !selectedMissionId
                      ? 'Load a mission first'
                      : launchVehicles.length === 0
                        ? 'Assign a vehicle or select a fleet'
                        : waypoints.length === 0
                          ? 'No waypoints to upload'
                          : isUploadingMission
                            ? 'Uploading...'
                            : undefined
                }
              >
                Upload
              </ActionButton>
              <ActionButton
                actionId="mission.download"
                size="xs"
                variant="secondary"
                icon={Download}
                loading={isDownloadingMission}
                onAction={handleDownloadMission}
                disabled={!canPilotMission || launchVehicles.length !== 1 || isDownloadingMission}
                disabledReason={
                  !canPilotMission
                    ? 'Pilot role required'
                    : launchVehicles.length === 0
                      ? 'Select a vehicle first'
                      : launchVehicles.length !== 1
                        ? 'Select exactly one vehicle'
                        : isDownloadingMission
                          ? 'Downloading...'
                          : undefined
                }
              >
                Download
              </ActionButton>
            </div>
          }>
            <CardTitle subtitle={`${waypoints.length} waypoints defined`}>Waypoint Editor</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {missionUploadError && (
              <div className="rounded-lg border border-red-600/30 bg-red-600/10 px-3 py-2 text-sm text-red-300">{missionUploadError}</div>
            )}
            {missionDownloadError && (
              <div className="rounded-lg border border-red-600/30 bg-red-600/10 px-3 py-2 text-sm text-red-300">{missionDownloadError}</div>
            )}
            <div className="rounded-xl overflow-hidden border border-slate-700">
              <div className="h-[430px]">
                <MapContainer
                  center={MAP_CONFIG.DEFAULT_CENTER}
                  zoom={MAP_CONFIG.DEFAULT_ZOOM}
                  className="w-full h-full"
                  style={{ background: '#0f172a' }}
                  zoomControl={false}
                  attributionControl={false}
                >
                  <TileLayer url={MAP_CONFIG.TILE_LAYER} attribution={MAP_CONFIG.TILE_ATTRIBUTION} maxZoom={MAP_CONFIG.MAX_ZOOM} />

                  <MapClickHandler
                    drawingGeofence={isDrawingGeofence}
                    addWaypointsOnClick={addWaypointsOnClick}
                    onAddGeofencePoint={(point) => setGeofencePoints((prev) => [...prev, point])}
                    onAddWaypoint={({ lat, lng }) => handleAddWaypoint({ lat, lng })}
                  />

                  {geofencePoints.length > 2 && (
                    <Polygon positions={geofencePoints.map((p) => [p.lat, p.lng])} pathOptions={{ color: '#22c55e', fillOpacity: 0.08 }} />
                  )}

                  {geofencePoints.map((p, idx) => (
                    <Marker
                      key={`geofence-${idx}`}
                      position={[p.lat, p.lng]}
                      draggable
                      eventHandlers={{
                        dragend: (ev) => handleGeofenceVertexDrag(idx, ev.target.getLatLng()),
                        contextmenu: () => handleRemoveGeofenceVertex(idx),
                      }}
                    >
                      <Popup>
                        <div className="space-y-2 text-xs">
                          <div>Vertex #{idx + 1}</div>
                          <Button size="xs" variant="danger" onClick={() => handleRemoveGeofenceVertex(idx)}>Remove Vertex</Button>
                        </div>
                      </Popup>
                    </Marker>
                  ))}

                  {path.length > 1 && <Polyline positions={path} color="#3b82f6" weight={2} dashArray="8,8" />}
                  {previewPath.length > 1 && <Polyline positions={previewPath} color="#22c55e" weight={2} dashArray="4,6" />}

                  {waypoints.map((wp, i) => (
                    <Marker
                      key={wp.id}
                      position={[wp.lat, wp.lng]}
                      icon={createWaypointIcon(i, { selected: wp.id === selectedWaypointId })}
                      draggable
                      eventHandlers={{
                        click: () => setSelectedWaypointId(wp.id),
                        dragend: (ev) => {
                          const p = ev.target.getLatLng();
                          updateWaypoint(wp.id, { lat: p.lat, lng: p.lng });
                        },
                      }}
                    />
                  ))}

                  {droneMarkers.map((drone) => (
                    <Marker
                      key={`drone-${drone.id}`}
                      position={[drone.lat, drone.lng]}
                      icon={createDroneIcon(drone.heading, drone.status, drone.type)}
                    >
                      <Popup>
                        <div className="space-y-2 text-xs text-slate-100 min-w-[190px]">
                          <div className="font-semibold text-sm">{drone.name}</div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-400">Status</span>
                            <span className="font-medium" style={{ color: DRONE_STATUS_COLORS[drone.status] }}>{DRONE_STATUS_LABELS[drone.status]}</span>
                          </div>
                          <div className="flex items-center justify-between"><span className="text-slate-400">Battery</span><span>{Math.round(drone.battery)}%</span></div>
                          <div className="flex items-center justify-between"><span className="text-slate-400">Altitude</span><span>{drone.altitude.toFixed(1)} m</span></div>
                          <div className="flex items-center justify-between"><span className="text-slate-400">Speed</span><span>{drone.speed.toFixed(1)} m/s</span></div>
                          <div className="flex items-center justify-between"><span className="text-slate-400">GPS quality</span><span>{drone.gpsQuality}</span></div>
                          <div className="flex items-center justify-between"><span className="text-slate-400">Link quality</span><span>{Math.round(drone.linkQuality)}%</span></div>
                          <div className="text-slate-500">{drone.callsign}</div>
                        </div>
                      </Popup>
                    </Marker>
                  ))}
                </MapContainer>
              </div>
              <div className="px-3 py-2 text-xs text-slate-400 bg-slate-900/40 border-t border-slate-700 flex flex-wrap gap-4">
                <span>
                  {isDrawingGeofence
                    ? 'Geofence mode: click to add vertices (Undo/Cancel available).'
                    : (addWaypointsOnClick
                      ? 'Waypoint mode: click to add waypoint.'
                      : 'Pan mode: Shift+Click to add waypoint.')}
                </span>
                <span>Drag waypoint markers or geofence vertices to edit. Right-click a geofence vertex to delete.</span>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-wider text-slate-500">Steps</span>
                <Button size="xs" variant={plannerStep === 'area' ? 'secondary' : 'ghost'} onClick={() => setPlannerStep('area')}>Area</Button>
                <Button size="xs" variant={plannerStep === 'route' ? 'secondary' : 'ghost'} onClick={() => setPlannerStep('route')}>Route</Button>
                <Button size="xs" variant={plannerStep === 'assign' ? 'secondary' : 'ghost'} onClick={() => setPlannerStep('assign')}>Assign</Button>
                <Button size="xs" variant={plannerStep === 'checks' ? 'secondary' : 'ghost'} onClick={() => setPlannerStep('checks')}>Checks</Button>
              </div>
              <div className="text-xs text-slate-500">
                {plannerStep === 'area'
                  ? 'Draw/adjust your geofence boundary.'
                  : plannerStep === 'route'
                    ? 'Generate grid or add/edit route waypoints.'
                    : plannerStep === 'assign'
                      ? 'Pick a fleet and launch policies.'
                      : 'Run pre-flight and sync start.'}
              </div>
            </div>
            {plannerStep === 'area' && (
              <div className="border border-slate-700 rounded-lg p-3 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-200">Polygon Geofence</h3>
                  <Badge color={missionValidation.valid ? 'green' : 'red'}>{missionValidation.valid ? 'Valid' : 'Invalid'}</Badge>
                </div>
                <div className="flex flex-wrap gap-2">
                  {!isDrawingGeofence ? (
                    <>
                      <Button size="sm" variant="outline" onClick={() => beginGeofenceEdit({ clear: geofencePoints.length === 0 })}>
                        {geofencePoints.length > 2 ? 'Edit Geofence' : 'Draw Geofence'}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => beginGeofenceEdit({ clear: true })}>
                        New Polygon
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button size="sm" variant="secondary" onClick={undoGeofencePoint} disabled={geofencePoints.length === 0}>Undo</Button>
                      <Button size="sm" variant="success" onClick={finishGeofenceEdit} disabled={geofencePoints.length < 3}>Finish</Button>
                      <Button size="sm" variant="ghost" onClick={cancelGeofenceEdit}>Cancel</Button>
                    </>
                  )}
                  <Button size="sm" variant="ghost" onClick={handleDeletePolygon} disabled={geofencePoints.length === 0}>Delete Polygon</Button>
                </div>
                <p className="text-xs text-slate-500">Vertices: {geofencePoints.length}. Mission start is blocked if any waypoint/path exits polygon.</p>
                {!missionValidation.valid && (
                  <div className="rounded border border-red-600/30 bg-red-600/10 p-2 text-xs text-red-300 space-y-1 max-h-28 overflow-auto">
                    {missionValidation.reasons.map((r) => <div key={r}>{r}</div>)}
                  </div>
                )}
              </div>
            )}

            {plannerStep === 'route' && (
              <>
                <div className="border border-slate-700 rounded-lg p-3 space-y-3">
                  <h3 className="text-sm font-semibold text-slate-200">Grid Survey Auto-Generation</h3>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[11px] text-slate-500 mb-1">Line spacing (m)</label>
                      <input
                        type="number"
                        step="1"
                        min="1"
                        className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
                        value={gridParams.lineSpacing}
                        onChange={(e) => setGridParams((p) => ({ ...p, lineSpacing: Number(e.target.value) || 1 }))}
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-500 mb-1">Heading (°)</label>
                      <input
                        type="number"
                        step="1"
                        className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
                        value={gridParams.headingAngle}
                        onChange={(e) => setGridParams((p) => ({ ...p, headingAngle: Number(e.target.value) || 0 }))}
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-500 mb-1">Altitude (m)</label>
                      <input
                        type="number"
                        step="1"
                        className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
                        value={gridParams.altitude}
                        onChange={(e) => setGridParams((p) => ({ ...p, altitude: Number(e.target.value) || 100 }))}
                      />
                    </div>
                    <div className="flex items-end">
                      <Button size="sm" variant="ghost" onClick={() => setGridParams(DEFAULT_GRID_PARAMS)}>Reset</Button>
                    </div>
                  </div>

                  <details className="rounded-lg border border-slate-700/60 bg-slate-900/20 p-2">
                    <summary className="text-xs text-slate-400 cursor-pointer select-none">Advanced</summary>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[11px] text-slate-500 mb-1">Overlap (%)</label>
                        <input
                          type="number"
                          step="1"
                          min="0"
                          className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
                          value={gridParams.overlapPercent}
                          onChange={(e) => setGridParams((p) => ({ ...p, overlapPercent: Number(e.target.value) || 0 }))}
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-slate-500 mb-1">Edge margin (m)</label>
                        <input
                          type="number"
                          step="1"
                          min="0"
                          className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
                          value={gridParams.edgeMargin}
                          onChange={(e) => setGridParams((p) => ({ ...p, edgeMargin: Number(e.target.value) || 0 }))}
                        />
                      </div>
                      <div className="col-span-2">
                        <label className="block text-[11px] text-slate-500 mb-1">Turnaround behavior</label>
                        <select
                          className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-300"
                          value={gridParams.turnaround}
                          onChange={(e) => setGridParams((p) => ({ ...p, turnaround: e.target.value }))}
                        >
                          <option value="inside_only">Inside only</option>
                          <option value="edge_pause">Edge pause</option>
                        </select>
                      </div>
                    </div>
                  </details>

                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={handleGenerateGridPreview}
                      disabled={geofencePoints.length < 3}
                    >
                      Preview Grid
                    </Button>
                    <Button size="sm" variant="success" onClick={handleApplyGridPreview} disabled={gridPreviewWaypoints.length === 0}>Apply Preview</Button>
                    <Button size="sm" variant="ghost" onClick={() => setGridPreviewWaypoints([])} disabled={gridPreviewWaypoints.length === 0}>Clear Preview</Button>
                  </div>
                  <p className="text-xs text-slate-500">Preview points: {gridPreviewWaypoints.length}. Grid is generated inside polygon only.</p>
                </div>

                <div className="border border-slate-700 rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-xs text-slate-500">Geofence</div>
                    <Badge color={geofencePoints.length >= 3 ? 'green' : 'red'}>{geofencePoints.length >= 3 ? 'Defined' : 'Missing'}</Badge>
                  </div>
                  <div className="text-xs text-slate-500">{geofencePoints.length >= 3 ? `${geofencePoints.length} vertices` : 'Draw a polygon in Area step to enable grid + validation.'}</div>
                </div>
              </>
            )}

            {plannerStep === 'assign' && (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <div className="border border-slate-700 rounded-lg p-3 space-y-3">
                  <h3 className="text-sm font-semibold text-slate-200">Policies</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Terrain fallback policy</label>
                      <select
                        className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-300"
                        value={terrainFallbackPolicy}
                        onChange={(e) => setTerrainFallbackPolicy(e.target.value)}
                      >
                        <option value="use_relative">Fallback to Relative altitude (warning)</option>
                        <option value="block_start">Block mission start if terrain unavailable</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Launch policy</label>
                      <select
                        className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-300"
                        value={launchPolicy}
                        onChange={(e) => setLaunchPolicy(e.target.value)}
                      >
                        <option value="all_or_none">All-or-none (default)</option>
                        <option value="launch_ready_only">Launch-ready-only</option>
                      </select>
                    </div>
                  </div>
                  {usesTerrainFollow && !terrainAvailable && (
                    <div className="flex items-start gap-2 text-xs rounded border border-amber-500/30 bg-amber-500/10 text-amber-200 p-2">
                      <ShieldAlert className="w-4 h-4 mt-0.5" />
                      <span>Terrain-follow is enabled on at least one waypoint, but terrain data is unavailable for selected launch drones. Policy: {terrainFallbackPolicy === 'block_start' ? 'block start' : 'fallback to relative'}.</span>
                    </div>
                  )}
                </div>

                <div className="border border-slate-700 rounded-lg p-3 space-y-3">
                  <h3 className="text-sm font-semibold text-slate-200">Fleet Assignment</h3>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Launch Fleet (optional)</label>
                    <select className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-2 text-sm text-slate-300" value={selectedFleetId} onChange={(e) => setSelectedFleetId(e.target.value)}>
                      <option value="">Use mission-assigned drones</option>
                      {fleets.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                    </select>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button size="sm" variant="outline" onClick={handleAssignFleet} disabled={!selectedFleetId || !selectedMissionId}>Assign Mission to Fleet</Button>
                    <Button size="sm" variant="secondary" onClick={openAssignForSelectedMission} disabled={!selectedMissionId}>Assign to Drones…</Button>
                  </div>
                  <p className="text-xs text-slate-500">If a fleet is selected, it overrides mission assignments for pre-flight + sync start.</p>
                </div>
              </div>
            )}

            {plannerStep === 'route' && (
              <div className="border border-slate-700 rounded-lg p-3 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold text-slate-200">Route Waypoints</h3>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] text-slate-500">{waypoints.length} waypoints</span>
                    <span className="text-[10px] uppercase tracking-wider text-slate-500">Map mode</span>
                    <Button size="xs" variant={!isDrawingGeofence && !addWaypointsOnClick ? 'secondary' : 'ghost'} onClick={() => { setIsDrawingGeofence(false); setAddWaypointsOnClick(false); }}>Pan</Button>
                    <Button size="xs" variant={!isDrawingGeofence && addWaypointsOnClick ? 'secondary' : 'ghost'} onClick={() => { setIsDrawingGeofence(false); setAddWaypointsOnClick(true); }}>Add</Button>
                    <Button size="xs" variant={isDrawingGeofence ? 'secondary' : 'ghost'} onClick={() => beginGeofenceEdit({ clear: geofencePoints.length === 0 })}>Geofence</Button>
                  </div>
                </div>

                <div className="text-xs text-slate-500">
                  {isDrawingGeofence ? 'Click to add vertices.' : (addWaypointsOnClick ? 'Click to add waypoint.' : 'Shift+Click to add waypoint.')}
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                  <div className="space-y-2 max-h-[340px] overflow-y-auto">
                    {waypoints.length === 0 ? (
                      <div className="text-sm text-slate-500 border border-dashed border-slate-700 rounded-lg p-3">
                        Add waypoints from the map (Add mode) or use Grid Preview.
                      </div>
                    ) : (
                      waypoints.map((wp, i) => (
                        <WaypointListItem
                          key={wp.id}
                          wp={wp}
                          index={i}
                          selected={wp.id === selectedWaypointId}
                          onSelect={() => setSelectedWaypointId(wp.id)}
                          onRemove={() => removeWaypoint(wp.id)}
                        />
                      ))
                    )}
                  </div>

                  <SelectedWaypointEditor
                    key={selectedWaypoint?.id || 'none'}
                    wp={selectedWaypoint}
                    index={selectedWaypointIndex}
                    allWaypoints={waypoints}
                    onUpdate={updateWaypoint}
                    onRemove={removeWaypoint}
                  />
                </div>

                <ActionButton
                  actionId="mission.waypoint.add"
                  onAction={handleAddWaypoint}
                  fullWidth
                  variant="outline"
                  className="w-full border-2 border-dashed border-slate-700 hover:border-blue-500/30"
                  icon={Plus}
                >
                  Add Waypoint
                </ActionButton>
              </div>
            )}

            {plannerStep === 'checks' && (
              <div className="rounded-lg border border-slate-700 bg-slate-800/30 p-3 text-sm text-slate-500">
                Open the Checks panel below to run pre-flight and start the fleet.
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {plannerStep === 'checks' && (
        <Card>
          <CardHeader action={
            <div className="flex items-center gap-2">
              <Button size="sm" variant="secondary" onClick={runPreflightChecks}>Run Pre-flight</Button>
              <Button
                size="sm"
                icon={Play}
                onClick={handleStartFleetMission}
                loading={isStartingMission}
                disabled={!canPilotMission || (readinessSummary.total > 0 && launchPolicy === 'all_or_none' && readinessSummary.ready < readinessSummary.total)}
                title={!canPilotMission ? 'Pilot role required' : undefined}
              >
                Sync Start
              </Button>
            </div>
          }>
            <CardTitle subtitle="Ready/Total, blockers, warnings across selected launch drones">Mission Readiness Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div className="text-xs text-slate-500">
                Targets: {launchVehicles.length} drone(s) ({selectedFleetId ? 'from fleet selection' : 'from mission assignments'})
              </div>
              <label className="flex items-center gap-2 text-xs text-slate-400 select-none">
                <input type="checkbox" checked={showInfoChecks} onChange={(e) => setShowInfoChecks(e.target.checked)} />
                Show INFO checks
              </label>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
                <div className="text-xs text-slate-500">Ready / Total</div>
                <div className="text-lg font-semibold text-slate-100">{readinessSummary.ready} / {readinessSummary.total}</div>
              </div>
              <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
                <div className="text-xs text-slate-500">Blockers</div>
                <div className="text-lg font-semibold text-red-400">{readinessSummary.blockers}</div>
              </div>
              <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
                <div className="text-xs text-slate-500">Warnings</div>
                <div className="text-lg font-semibold text-amber-400">{readinessSummary.warnings}</div>
              </div>
            </div>

            {missionStartError && (
              <div className="rounded-lg border border-red-600/30 bg-red-600/10 px-3 py-2 text-sm text-red-300">{missionStartError}</div>
            )}

            {preflightResults.length === 0 ? (
              <div className="text-sm text-slate-500">Run pre-flight checks to see per-drone blockers, warnings, and fix hints.</div>
            ) : (
              <div className="space-y-2 max-h-[520px] overflow-y-auto">
                {preflightResults.map((result) => {
                  const visibleChecks = showInfoChecks
                    ? result.checks
                    : result.checks.filter((c) => c.level !== 'INFO');

                  return (
                    <details key={result.vehicleId} className="border border-slate-700 rounded-lg bg-slate-800/60" open={result.blockers > 0}>
                      <summary className="cursor-pointer select-none px-3 py-2">
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm font-semibold text-slate-200">{result.vehicleName}</div>
                          <div className="flex items-center gap-2 text-xs">
                            {result.blockers === 0 ? (
                              <span className="inline-flex items-center gap-1 text-emerald-300"><ShieldCheck className="w-3.5 h-3.5" /> Ready</span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-red-300"><ShieldAlert className="w-3.5 h-3.5" /> Blocked</span>
                            )}
                            <span className="text-red-300">B:{result.blockers}</span>
                            <span className="text-amber-300">W:{result.warnings}</span>
                          </div>
                        </div>
                      </summary>
                      <div className="px-3 pb-3">
                        {visibleChecks.length === 0 ? (
                          <div className="text-sm text-slate-500">No blockers/warnings.</div>
                        ) : (
                          <div className="space-y-2">
                            {visibleChecks.map((check) => (
                              <div key={`${result.vehicleId}-${check.name}`} className="rounded border border-slate-700 bg-slate-900/60 p-2">
                                <div className="flex items-center justify-between text-xs">
                                  <span className="uppercase tracking-wide text-slate-400">{check.name}</span>
                                  <span className={`font-semibold ${check.level === 'BLOCKER' ? 'text-red-400' : check.level === 'WARNING' ? 'text-amber-400' : 'text-emerald-400'}`}>{check.level}</span>
                                </div>
                                <div className="text-xs text-slate-200 mt-1">{check.message}</div>
                                <div className="text-[11px] text-slate-500 mt-0.5">Hint: {check.hint}</div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </details>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Modal
        isOpen={showNewMission}
        onClose={() => setShowNewMission(false)}
        title="Create New Mission"
        size="md"
        footer={(
          <>
            <ActionButton actionId="nav.goto.dashboard" variant="secondary" onAction={() => setShowNewMission(false)}>Cancel</ActionButton>
            <ActionButton actionId="mission.create" onAction={handleSaveMission}>Create Mission</ActionButton>
          </>
        )}
      >
        <div className="space-y-4">
          <Input label="Mission Name" placeholder="e.g., Perimeter Survey Alpha" value={missionName} onChange={(e) => setMissionName(e.target.value)} />
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Mission Type</label>
            <select className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-slate-300" value={missionType} onChange={(e) => setMissionType(e.target.value)}>
              <option value="waypoint">Waypoint</option>
              <option value="survey">Survey</option>
              <option value="corridor">Corridor</option>
              <option value="orbit">Orbit</option>
            </select>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={showEditMission}
        onClose={() => setShowEditMission(false)}
        title="Edit Mission"
        size="md"
        footer={(
          <>
            <ActionButton actionId="nav.goto.dashboard" variant="secondary" onAction={() => setShowEditMission(false)}>Cancel</ActionButton>
            <ActionButton actionId="mission.update" onAction={handleSaveMission}>Save Changes</ActionButton>
          </>
        )}
      >
        <div className="space-y-4">
          <Input label="Mission Name" placeholder="e.g., Perimeter Survey Alpha" value={missionName} onChange={(e) => setMissionName(e.target.value)} />
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Mission Type</label>
            <select className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-slate-300" value={missionType} onChange={(e) => setMissionType(e.target.value)}>
              <option value="waypoint">Waypoint</option>
              <option value="survey">Survey</option>
              <option value="corridor">Corridor</option>
              <option value="orbit">Orbit</option>
            </select>
          </div>
          {editingMission && (
            <div className="text-xs text-slate-500">
              Editing mission: <span className="text-slate-300">{editingMission.name}</span>
            </div>
          )}
        </div>
      </Modal>

      <Modal
        isOpen={showAssignModal}
        onClose={() => setShowAssignModal(false)}
        title="Assign Mission to Vehicles"
        size="md"
        footer={(
          <>
            <ActionButton actionId="nav.goto.dashboard" variant="secondary" onAction={() => setShowAssignModal(false)}>Cancel</ActionButton>
            <ActionButton actionId="mission.assign" onAction={handleAssignMission}>
              {assignVehicleIds.length ? 'Save Assignment' : 'Unassign All'}
            </ActionButton>
          </>
        )}
      >
        <div className="space-y-3">
          <p className="text-sm text-slate-400">Select one or more vehicles to bind this mission.</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {vehicles.map((v) => (
              <button
                key={v.id}
                onClick={() =>
                  setAssignVehicleIds((prev) =>
                    prev.includes(v.id) ? prev.filter((id) => id !== v.id) : [...prev, v.id]
                  )
                }
                className={`p-3 rounded-lg border text-sm text-left transition-colors ${
                  assignVehicleIds.includes(v.id)
                    ? 'border-blue-500/50 bg-blue-600/10 text-blue-200'
                    : 'border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700/40'
                }`}
              >
                <div className="font-medium">{v.name}</div>
                <div className="text-xs text-slate-500">{v.callsign}</div>
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Unlink className="w-4 h-4" />
            Clear all selections to unassign the mission from all vehicles.
          </div>
        </div>
      </Modal>
    </div>
  );
}

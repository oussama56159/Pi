import { create } from 'zustand';
import { missionAPI } from '@/lib/api/endpoints';

const MOCK_MODE_KEY = 'aero_mock_mode';

const isMockMode = () => {
  if (typeof window !== 'undefined') {
    const stored = window.localStorage.getItem(MOCK_MODE_KEY);
    if (stored !== null) return stored === 'true';
  }
  return import.meta.env.VITE_MOCK_MODE === 'true';
};

const normalizeWaypoint = (waypoint, index) => {
  const altValue = Number(waypoint?.alt ?? waypoint?.altitude ?? 100);
  return {
    ...waypoint,
    id: waypoint?.id || crypto.randomUUID(),
    seq: Number.isFinite(Number(waypoint?.seq)) ? Number(waypoint.seq) : index,
    lat: Number(waypoint?.lat) || 0,
    lng: Number(waypoint?.lng) || 0,
    alt: Number.isFinite(altValue) ? altValue : 100,
    altitude_mode: waypoint?.altitude_mode || waypoint?.altMode || 'relative',
    command: waypoint?.command || 'NAV_WAYPOINT',
    frame: Number.isFinite(Number(waypoint?.frame)) ? Number(waypoint.frame) : 3,
    param1: Number.isFinite(Number(waypoint?.param1)) ? Number(waypoint.param1) : 0,
    param2: Number.isFinite(Number(waypoint?.param2)) ? Number(waypoint.param2) : 0,
    param3: Number.isFinite(Number(waypoint?.param3)) ? Number(waypoint.param3) : 0,
    param4: Number.isFinite(Number(waypoint?.param4)) ? Number(waypoint.param4) : 0,
  };
};

const normalizeWaypoints = (waypoints = []) => waypoints.map((wp, i) => normalizeWaypoint(wp, i));

export const useMissionStore = create((set, get) => ({
  missions: [],
  selectedMissionId: null,
  activeMission: null,
  waypoints: [],
  isLoading: false,
  error: null,

  fetchMissions: async (params) => {
    if (isMockMode()) {
      set({ isLoading: false, error: null });
      return;
    }
    set({ isLoading: true, error: null });
    try {
      const { data } = await missionAPI.list(params);
      set({ missions: data.items || data, isLoading: false });
    } catch (err) {
      set({ error: err.message, isLoading: false });
    }
  },

  fetchMission: async (id) => {
    if (isMockMode()) {
      const mission = get().missions.find((m) => m.id === id) || null;
      set({ activeMission: mission, waypoints: normalizeWaypoints(mission?.waypoints || []), isLoading: false, error: null });
      return mission;
    }
    set({ isLoading: true, error: null });
    try {
      const { data } = await missionAPI.get(id);
      set((state) => ({
        activeMission: data,
        waypoints: normalizeWaypoints(data.waypoints || []),
        missions: state.missions.map((m) => (m.id === id ? data : m)),
        isLoading: false,
      }));
      return data;
    } catch (err) {
      set({ error: err.message, isLoading: false });
    }
  },

  assignMission: async (missionId, vehicleIds, options = {}) => {
    if (isMockMode()) {
      set((state) => ({
        missions: state.missions.map((m) => (
          m.id === missionId
            ? { ...m, assigned_vehicle_ids: vehicleIds, assignments: vehicleIds.map((vid) => ({ vehicle_id: vid, active: true, status: 'ready', progress: 0 })) }
            : m
        )),
      }));
      return;
    }
    const payload = { vehicle_ids: vehicleIds, replace_existing: options.replaceExisting ?? true };
    const { data } = await missionAPI.assign(missionId, payload);
    set((state) => ({
      missions: state.missions.map((m) => (
        m.id === missionId
          ? {
            ...m,
            assignments: [...(m.assignments || []).filter((a) => !vehicleIds.includes(a.vehicle_id)), ...data],
            assigned_vehicle_ids: Array.from(new Set([...(m.assigned_vehicle_ids || []), ...vehicleIds])),
          }
          : m
      )),
      activeMission: state.activeMission?.id === missionId
        ? {
          ...state.activeMission,
          assignments: [...(state.activeMission.assignments || []).filter((a) => !vehicleIds.includes(a.vehicle_id)), ...data],
          assigned_vehicle_ids: Array.from(new Set([...(state.activeMission.assigned_vehicle_ids || []), ...vehicleIds])),
        }
        : state.activeMission,
    }));
  },

  unassignMission: async (missionId, vehicleIds) => {
    if (isMockMode()) {
      set((state) => ({
        missions: state.missions.map((m) => (
          m.id === missionId
            ? {
              ...m,
              assignments: (m.assignments || []).map((a) => (vehicleIds.includes(a.vehicle_id) ? { ...a, active: false } : a)),
              assigned_vehicle_ids: (m.assigned_vehicle_ids || []).filter((id) => !vehicleIds.includes(id)),
            }
            : m
        )),
      }));
      return;
    }
    await missionAPI.unassign(missionId, { vehicle_ids: vehicleIds });
    set((state) => ({
      missions: state.missions.map((m) => (
        m.id === missionId
          ? {
            ...m,
            assignments: (m.assignments || []).map((a) => (vehicleIds.includes(a.vehicle_id) ? { ...a, active: false } : a)),
            assigned_vehicle_ids: (m.assigned_vehicle_ids || []).filter((id) => !vehicleIds.includes(id)),
          }
          : m
      )),
      activeMission: state.activeMission?.id === missionId
        ? {
          ...state.activeMission,
          assignments: (state.activeMission.assignments || []).map((a) => (vehicleIds.includes(a.vehicle_id) ? { ...a, active: false } : a)),
          assigned_vehicle_ids: (state.activeMission.assigned_vehicle_ids || []).filter((id) => !vehicleIds.includes(id)),
        }
        : state.activeMission,
    }));
  },

  createMission: async (missionData) => {
    const normalizedPayload = {
      ...missionData,
      waypoints: normalizeWaypoints(missionData?.waypoints || []),
    };
    if (isMockMode()) {
      const mockMission = {
        ...normalizedPayload,
        id: crypto.randomUUID(),
        status: missionData.status || 'planned',
        progress: 0,
        createdAt: new Date().toISOString(),
      };
      set((state) => ({ missions: [mockMission, ...state.missions], isLoading: false, error: null }));
      return mockMission;
    }
    set({ isLoading: true, error: null });
    try {
      const { data } = await missionAPI.create(normalizedPayload);
      set((state) => ({ missions: [...state.missions, data], isLoading: false }));
      return data;
    } catch (err) {
      set({ error: err.message, isLoading: false });
      throw err;
    }
  },

  updateMission: async (missionId, updates) => {
    const normalizedUpdates = updates?.waypoints
      ? { ...updates, waypoints: normalizeWaypoints(updates.waypoints) }
      : updates;
    if (isMockMode()) {
      set((state) => ({
        missions: state.missions.map((m) => (m.id === missionId ? { ...m, ...normalizedUpdates } : m)),
        activeMission: state.activeMission?.id === missionId ? { ...state.activeMission, ...normalizedUpdates } : state.activeMission,
        isLoading: false,
        error: null,
      }));
      return get().missions.find((m) => m.id === missionId);
    }
    set({ isLoading: true, error: null });
    try {
      const { data } = await missionAPI.update(missionId, normalizedUpdates);
      set((state) => ({
        missions: state.missions.map((m) => (m.id === missionId ? data : m)),
        activeMission: state.activeMission?.id === missionId ? data : state.activeMission,
        isLoading: false,
      }));
      return data;
    } catch (err) {
      set({ error: err.message, isLoading: false });
      throw err;
    }
  },

  deleteMission: async (missionId) => {
    if (isMockMode()) {
      set((state) => ({
        missions: state.missions.filter((m) => m.id !== missionId),
        activeMission: state.activeMission?.id === missionId ? null : state.activeMission,
        isLoading: false,
        error: null,
      }));
      return;
    }
    set({ isLoading: true, error: null });
    try {
      await missionAPI.delete(missionId);
      set((state) => ({
        missions: state.missions.filter((m) => m.id !== missionId),
        activeMission: state.activeMission?.id === missionId ? null : state.activeMission,
        isLoading: false,
      }));
    } catch (err) {
      set({ error: err.message, isLoading: false });
      throw err;
    }
  },

  selectMission: (id) => set({ selectedMissionId: id }),

  addWaypoint: (waypoint) => {
    set((state) => ({
      waypoints: [...state.waypoints, normalizeWaypoint({ ...waypoint, seq: state.waypoints.length }, state.waypoints.length)],
    }));
  },

  updateWaypoint: (id, updates) => {
    set((state) => ({
      waypoints: state.waypoints.map((wp) => (wp.id === id ? { ...wp, ...updates } : wp)),
    }));
  },

  removeWaypoint: (id) => {
    set((state) => ({
      waypoints: state.waypoints.filter((wp) => wp.id !== id).map((wp, i) => ({ ...wp, seq: i })),
    }));
  },

  reorderWaypoints: (startIdx, endIdx) => {
    set((state) => {
      const wps = [...state.waypoints];
      const [removed] = wps.splice(startIdx, 1);
      wps.splice(endIdx, 0, removed);
      return { waypoints: wps.map((wp, i) => ({ ...wp, seq: i })) };
    });
  },

  clearWaypoints: () => set({ waypoints: [] }),

  getMissionById: (id) => get().missions.find((m) => m.id === id),

  getActiveMissionForVehicle: (vehicleId) => {
    return get().missions.find((m) => (m.assignments || []).some((a) => a.vehicle_id === vehicleId && a.active));
  },

  applyAssignmentUpdate: (update) => {
    if (!update?.mission_id || !update?.vehicle_id) return;
    set((state) => ({
      missions: state.missions.map((m) => {
        if (m.id !== update.mission_id) return m;
        const assignments = (m.assignments || []).map((a) =>
          a.vehicle_id === update.vehicle_id ? { ...a, ...update } : a
        );
        const assignedIds = assignments.filter((a) => a.active).map((a) => a.vehicle_id);
        return { ...m, assignments, assigned_vehicle_ids: assignedIds };
      }),
      activeMission: state.activeMission?.id === update.mission_id
        ? {
          ...state.activeMission,
          assignments: (state.activeMission.assignments || []).map((a) =>
            a.vehicle_id === update.vehicle_id ? { ...a, ...update } : a
          ),
          assigned_vehicle_ids: (state.activeMission.assignments || [])
            .map((a) => (a.vehicle_id === update.vehicle_id ? { ...a, ...update } : a))
            .filter((a) => a.active)
            .map((a) => a.vehicle_id),
        }
        : state.activeMission,
    }));
  },
}));


import axios from 'axios';
import apiClient from './client';

const withIdempotencyHeaders = () => ({ headers: { 'Idempotency-Key': crypto.randomUUID() } });

// ─── Auth Endpoints ───
export const authAPI = {
  login: (credentials) => apiClient.post('/auth/login', credentials),
  register: (data) => apiClient.post('/auth/register', data),
  logout: () => apiClient.post('/auth/logout'),
  refreshToken: (token) => apiClient.post('/auth/refresh', { refresh_token: token }),
  me: () => apiClient.get('/auth/me'),
  changePassword: (data) => apiClient.put('/auth/password', data),
  requestPasswordRecovery: (data) => apiClient.post('/auth/password-recovery-request', data),
};

// ─── Fleet / Vehicle Endpoints ───
export const vehicleAPI = {
  list: (params) => apiClient.get('/fleet/vehicles', { params }),
  get: (id) => apiClient.get(`/fleet/vehicles/${id}`),
  create: (data) => apiClient.post('/fleet/vehicles', data),
  update: (id, data) => apiClient.patch(`/fleet/vehicles/${id}`, data),
  delete: (id) => apiClient.delete(`/fleet/vehicles/${id}`),
  telemetry: (id) => apiClient.get(`/telemetry/vehicles/${id}/latest`),
  telemetryHistory: (id, params) => apiClient.get(`/telemetry/vehicles/${id}/history`, { params }),
  sendCommand: (id, command) => apiClient.post('/commands', { vehicle_id: id, ...command }, withIdempotencyHeaders()),
  getParameters: (id) => apiClient.get(`/fleet/vehicles/${id}/parameters`),
  setParameter: (id, param) => apiClient.put(`/fleet/vehicles/${id}/parameters`, param),
};

// ─── Fleet Group Endpoints ───
export const fleetAPI = {
  list: (params) => apiClient.get('/fleet/fleets', { params }),
  get: (id) => apiClient.get(`/fleet/fleets/${id}`),
  create: (data) => apiClient.post('/fleet/fleets', data),
  update: (id, data) => apiClient.put(`/fleet/fleets/${id}`, data),
  delete: (id) => apiClient.delete(`/fleet/fleets/${id}`),
  addVehicle: (fleetId, vehicleId) => apiClient.post(`/fleet/fleets/${fleetId}/vehicles/${vehicleId}`),
  removeVehicle: (fleetId, vehicleId) => apiClient.delete(`/fleet/fleets/${fleetId}/vehicles/${vehicleId}`),
  sendGroupCommand: (fleetId, command) => apiClient.post(`/fleet/fleets/${fleetId}/command`, command),
};

// ─── Mission Endpoints ───
export const missionAPI = {
  list: (params) => apiClient.get('/missions', { params }),
  get: (id) => apiClient.get(`/missions/${id}`),
  create: (data) => apiClient.post('/missions', data),
  update: (id, data) => apiClient.patch(`/missions/${id}`, data),
  delete: (id) => apiClient.delete(`/missions/${id}`),
  assign: (id, data) => apiClient.post(`/missions/${id}/assign`, data),
  unassign: (id, data) => apiClient.post(`/missions/${id}/unassign`, data),
  assignments: (id) => apiClient.get(`/missions/${id}`),
  status: (data) => apiClient.post('/missions/status', data),
  upload: (vehicleId, missionId) => apiClient.post('/missions/upload', { vehicle_id: vehicleId, mission_id: missionId }),
  download: (vehicleId, name) => apiClient.post('/missions/download', { vehicle_id: vehicleId, ...(name ? { name } : {}) }),
  start: (vehicleId, missionId) => apiClient.post('/commands', { vehicle_id: vehicleId, command: 'mission_start', params: { mission_id: missionId } }, withIdempotencyHeaders()),
  pause: (vehicleId) => apiClient.post('/commands', { vehicle_id: vehicleId, command: 'mission_pause' }, withIdempotencyHeaders()),
  resume: (vehicleId) => apiClient.post('/commands', { vehicle_id: vehicleId, command: 'mission_resume' }, withIdempotencyHeaders()),
  getTemplates: () => apiClient.get('/missions/templates'),
};

// ─── Alerts Endpoints ───
export const alertAPI = {
  list: (params) => apiClient.get('/alerts', { params }),
  get: (id) => apiClient.get(`/alerts/${id}`),
  acknowledge: (id) => apiClient.post(`/alerts/${id}/acknowledge`),
  dismiss: (id) => apiClient.post(`/alerts/${id}/resolve`),
  getStats: () => apiClient.get('/alerts/stats'),
};

// ─── Analytics Endpoints ───
export const analyticsAPI = {
  fleetStats: (params) => apiClient.get('/analytics/fleet', { params }),
  vehicleStats: (id, params) => apiClient.get(`/analytics/vehicles/${id}`, { params }),
  missionStats: (params) => apiClient.get('/analytics/missions', { params }),
  flightHours: (params) => apiClient.get('/analytics/flight-hours', { params }),
  incidentReport: (params) => apiClient.get('/analytics/incidents', { params }),
};

// ─── User Management Endpoints ───
export const userAPI = {
  list: (params) => apiClient.get('/auth/users', { params }),
  get: (id) => apiClient.get(`/auth/users/${id}`),
  create: (data) => apiClient.post('/auth/users', data),
  update: (id, data) => apiClient.put(`/auth/users/${id}`, data),
  updatePassword: (id, password) => apiClient.put(`/auth/users/${id}/password`, { password }),
  deactivate: (id) => apiClient.delete(`/auth/users/${id}`),
  getRoles: () => apiClient.get('/auth/roles'),
  getAuditLog: (params) => apiClient.get('/auth/audit-log', { params }),
};

export const organizationAPI = {
  list: (params) => apiClient.get('/auth/organizations', { params }),
  get: (id) => apiClient.get(`/auth/organizations/${id}`),
  create: (data) => apiClient.post('/auth/organizations', data),
  update: (id, data) => apiClient.put(`/auth/organizations/${id}`, data),
  deactivate: (id) => apiClient.delete(`/auth/organizations/${id}`),
};

// ─── Fleet User Assignment Endpoints ───
export const fleetUserAPI = {
  listFleetUsers: (fleetId) => apiClient.get(`/fleet/fleets/${fleetId}/users`),
  assignUsers: (fleetId, data) => apiClient.post(`/fleet/fleets/${fleetId}/users`, data),
  removeUser: (fleetId, userId) => apiClient.delete(`/fleet/fleets/${fleetId}/users/${userId}`),
  listUserFleets: (userId) => apiClient.get(`/fleet/users/${userId}/fleets`),
};

// ─── System Endpoints ───
export const systemAPI = {
  health: () => axios.get('/health/ready'),
  config: () => apiClient.get('/system/config'),
  updateConfig: (data) => apiClient.put('/system/config', data),
  getLogs: (params) => apiClient.get('/system/logs', { params }),
};

// ─── Vision Endpoints ───
export const visionAPI = {
  start: (vehicleId, sourceUrl) => apiClient.post(`/vision/streams/${vehicleId}/start`, { source_url: sourceUrl }),
  stop: (vehicleId) => apiClient.post(`/vision/streams/${vehicleId}/stop`),
  latest: (vehicleId) => apiClient.get(`/vision/streams/${vehicleId}/detections/latest`),
};


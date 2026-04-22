export const MISSION_TYPES = [
  { value: 'cattle_surveillance', label: 'Cattle Surveillance' },
  { value: 'crop_surveillance', label: 'Crop Surveillance' },
  { value: 'farm_surveillance', label: 'Farm Surveillance' },
  { value: 'farm_security', label: 'Farm Security' },
];

const DEFAULT_MISSION_TYPE = 'crop_surveillance';

const MISSION_TYPE_LABELS = Object.fromEntries(
  MISSION_TYPES.map((item) => [item.value, item.label])
);

function _coerceString(value) {
  if (value === null || value === undefined) return '';
  return String(value);
}

export function normalizeMissionType(value) {
  const raw = _coerceString(value).trim();
  if (!raw) return DEFAULT_MISSION_TYPE;

  const slug = raw
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
    .replace(/[^a-z0-9_]/g, '');

  if (MISSION_TYPE_LABELS[slug]) return slug;

  const matchByLabel = MISSION_TYPES.find((item) => item.label.toLowerCase() === raw.toLowerCase());
  if (matchByLabel) return matchByLabel.value;

  return DEFAULT_MISSION_TYPE;
}

export function formatMissionType(value) {
  const normalized = normalizeMissionType(value);
  return MISSION_TYPE_LABELS[normalized] || 'Mission';
}

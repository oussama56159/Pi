import { useMemo, useState } from 'react';
import {
  Bell, Search, Filter, CalendarDays, AlertTriangle, XCircle,
  Info, CheckCircle, ArrowUpDown, Inbox,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import Card, { CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';
import Input, { Select } from '@/components/ui/Input';
import { useTelemetryStore } from '@/stores/telemetryStore';
import { useFleetStore } from '@/stores/fleetStore';

const typeOptions = [
  { value: 'all', label: 'All types' },
  { value: 'critical', label: 'Critical' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' },
  { value: 'success', label: 'Success' },
  { value: 'emergency', label: 'Emergency' },
  { value: 'battery', label: 'Battery' },
  { value: 'geofence', label: 'Geofence' },
  { value: 'connection', label: 'Connection' },
  { value: 'system', label: 'System' },
  { value: 'mission', label: 'Mission' },
  { value: 'sensor', label: 'Sensor' },
  { value: 'weather', label: 'Weather' },
  { value: 'custom', label: 'Custom' },
];

const severityStyles = {
  critical: { icon: XCircle, badge: 'red', text: 'text-red-400', border: 'border-red-500/20', bg: 'bg-red-500/10' },
  emergency: { icon: XCircle, badge: 'red', text: 'text-red-400', border: 'border-red-500/20', bg: 'bg-red-500/10' },
  warning: { icon: AlertTriangle, badge: 'amber', text: 'text-amber-400', border: 'border-amber-500/20', bg: 'bg-amber-500/10' },
  info: { icon: Info, badge: 'blue', text: 'text-blue-400', border: 'border-blue-500/20', bg: 'bg-blue-500/10' },
  success: { icon: CheckCircle, badge: 'green', text: 'text-emerald-400', border: 'border-emerald-500/20', bg: 'bg-emerald-500/10' },
};

const categoryBadgeColor = {
  battery: 'amber',
  geofence: 'purple',
  connection: 'cyan',
  system: 'gray',
  mission: 'blue',
  sensor: 'green',
  weather: 'cyan',
  custom: 'gray',
};

function formatDateInputValue(value) {
  if (!value) return '';
  return String(value).slice(0, 10);
}

function getNotificationType(notification) {
  return String(notification.category || notification.type || notification.severity || 'info').toLowerCase();
}

function getNotificationTime(notification) {
  const rawTime = notification.receivedAt || notification.timestamp || notification.created_at || notification.createdAt;
  const parsed = rawTime ? new Date(rawTime) : new Date(0);
  return Number.isNaN(parsed.getTime()) ? new Date(0) : parsed;
}

function getNotificationTitle(notification) {
  return notification.title || notification.subject || notification.message || 'Notification';
}

export default function NotificationHistoryPage() {
  const alerts = useTelemetryStore((s) => s.alerts);
  const unreadCount = useTelemetryStore((s) => s.unreadAlertCount);
  const vehicles = useFleetStore((s) => s.vehicles);

  const [search, setSearch] = useState('');
  const [type, setType] = useState('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const notifications = useMemo(() => {
    return [...alerts]
      .map((alert) => {
        const notificationType = getNotificationType(alert);
        const notificationTime = getNotificationTime(alert);
        const severity = String(alert.severity || notificationType || 'info').toLowerCase();
        const category = String(alert.category || '').toLowerCase();
        const vehicleName = vehicles.find((vehicle) => vehicle.id === alert.vehicle_id)?.name || vehicles.find((vehicle) => vehicle.id === alert.vehicleId)?.name || null;

        return {
          ...alert,
          type: notificationType,
          severity,
          category,
          vehicleName,
          notificationTime,
          title: getNotificationTitle(alert),
        };
      })
      .sort((left, right) => right.notificationTime.getTime() - left.notificationTime.getTime());
  }, [alerts, vehicles]);

  const filteredNotifications = useMemo(() => {
    const query = search.trim().toLowerCase();
    const start = startDate ? new Date(`${startDate}T00:00:00`) : null;
    const end = endDate ? new Date(`${endDate}T23:59:59.999`) : null;

    return notifications.filter((notification) => {
      const matchesQuery = !query || [
        notification.title,
        notification.message,
        notification.vehicleName,
        notification.category,
        notification.severity,
        notification.type,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query));

      const matchesType = type === 'all'
        || notification.type === type
        || notification.severity === type
        || notification.category === type;

      const notificationMillis = notification.notificationTime.getTime();
      const matchesStart = !start || notificationMillis >= start.getTime();
      const matchesEnd = !end || notificationMillis <= end.getTime();

      return matchesQuery && matchesType && matchesStart && matchesEnd;
    });
  }, [endDate, notifications, search, startDate, type]);

  const stats = useMemo(() => {
    const now = Date.now();
    const startOfToday = new Date();
    startOfToday.setHours(0, 0, 0, 0);

    return {
      total: notifications.length,
      unread: unreadCount,
      critical: notifications.filter((notification) => ['critical', 'emergency'].includes(notification.severity) && !notification.acknowledged).length,
      today: notifications.filter((notification) => notification.notificationTime.getTime() >= startOfToday.getTime()).length,
      recent: notifications.filter((notification) => now - notification.notificationTime.getTime() <= 24 * 60 * 60 * 1000).length,
    };
  }, [notifications, unreadCount]);

  const resetFilters = () => {
    setSearch('');
    setType('all');
    setStartDate('');
    setEndDate('');
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-blue-400 mb-2">
            <Bell className="w-5 h-5" />
            <span className="text-xs font-semibold uppercase tracking-[0.2em]">Notifications</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-100">Notification History</h1>
          <p className="text-sm text-slate-400 mt-1">
            Browse every notification delivered to this account, then narrow them by date, type, and keyword.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Link
            to="/app/alerts"
            className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg border border-slate-600 text-sm font-medium text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <ArrowUpDown className="w-4 h-4" />
            Open Alerts
          </Link>
          <Button variant="secondary" size="sm" icon={Filter} onClick={resetFilters}>
            Reset Filters
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-5 gap-4">
        {[
          { label: 'Total', value: stats.total, color: 'blue' },
          { label: 'Unread', value: stats.unread, color: 'amber' },
          { label: 'Critical', value: stats.critical, color: 'red' },
          { label: 'Today', value: stats.today, color: 'green' },
          { label: 'Last 24h', value: stats.recent, color: 'cyan' },
        ].map((card) => (
          <Card key={card.label}>
            <p className="text-sm text-slate-400">{card.label}</p>
            <p className={`text-2xl font-bold mt-1 text-${card.color}-400`}>{card.value}</p>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader action={<Badge color="blue">Filtered: {filteredNotifications.length}</Badge>}>
          <CardTitle subtitle="Search, type and date filters">Filter history</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          <Input
            label="Search"
            icon={Search}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by title, message, vehicle..."
          />
          <Select
            label="Type"
            value={type}
            onChange={(event) => setType(event.target.value)}
            options={typeOptions}
          />
          <Input
            label="From date"
            type="date"
            value={formatDateInputValue(startDate)}
            onChange={(event) => setStartDate(event.target.value)}
          />
          <Input
            label="To date"
            type="date"
            value={formatDateInputValue(endDate)}
            onChange={(event) => setEndDate(event.target.value)}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader action={<Badge color={filteredNotifications.length > 0 ? 'green' : 'gray'}>{filteredNotifications.length} results</Badge>}>
          <CardTitle subtitle="Chronological view of all notifications">History</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {filteredNotifications.map((notification) => {
            const style = severityStyles[notification.severity] || severityStyles.info;
            const Icon = style.icon;
            const categoryColor = notification.category ? categoryBadgeColor[notification.category] || 'gray' : null;
            return (
              <div
                key={notification.id}
                className={`flex gap-4 p-4 rounded-xl border ${style.bg} ${style.border} ${notification.acknowledged ? 'opacity-70' : ''}`}
              >
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 bg-slate-900/60 border border-slate-700 ${style.text}`}>
                  <Icon className="w-5 h-5" />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <Badge color={style.badge}>{notification.severity}</Badge>
                    {notification.category && notification.category !== notification.severity && (
                      <Badge color={categoryColor || 'gray'}>{notification.category}</Badge>
                    )}
                    {notification.vehicleName && <Badge color="cyan">{notification.vehicleName}</Badge>}
                    {notification.acknowledged && <Badge color="green">Read</Badge>}
                  </div>

                  <h3 className="text-sm font-semibold text-slate-100">{notification.title}</h3>
                  <p className="mt-1 text-sm text-slate-300 leading-6">{notification.message}</p>

                  <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-500">
                    <span className="inline-flex items-center gap-1">
                      <CalendarDays className="w-3.5 h-3.5" />
                      {notification.notificationTime.toLocaleString()}
                    </span>
                    <span>ID {notification.id}</span>
                  </div>
                </div>
              </div>
            );
          })}

          {filteredNotifications.length === 0 && (
            <div className="text-center py-16">
              <Inbox className="w-12 h-12 text-slate-600 mx-auto mb-3" />
              <p className="text-slate-300 font-medium">No notifications match these filters</p>
              <p className="text-sm text-slate-500 mt-1">Try a different date range, type, or keyword.</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
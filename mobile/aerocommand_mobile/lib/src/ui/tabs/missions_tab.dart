import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'dart:async';

import '../../api/api_client.dart';
import '../../auth/auth_controller.dart';
import '../../models/fleet_model.dart';
import '../../models/mission_model.dart';
import '../../models/vehicle_model.dart';
import '../../mock/demo_repository.dart';
import '../widgets/drone_logo.dart';

class MissionsTab extends StatefulWidget {
  const MissionsTab({super.key});

  @override
  State<MissionsTab> createState() => _MissionsTabState();
}

class _MissionsTabState extends State<MissionsTab> {
  bool _loading = true;
  String? _error;

  List<MissionModel> _missions = const [];
  List<VehicleModel> _vehicles = const [];
  List<FleetModel> _fleets = const [];

  final Set<String> _selectedMissionIds = {};
  final Set<String> _selectedVehicleIds = {};

  String _targetMode = 'vehicles'; // or 'fleet'
  String? _selectedFleetId;

  bool _assigning = false;

  Timer? _demoRefreshTimer;

  String _idempotencyKey(String vehicleId, String missionId) {
    final ts = DateTime.now().toUtc().microsecondsSinceEpoch;
    return 'mobile-$vehicleId-$missionId-$ts';
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final auth = context.watch<AuthController>();

    if (auth.isDemo) {
      _demoRefreshTimer ??= Timer.periodic(const Duration(seconds: 2), (_) {
        if (!mounted) return;
        _loadMissionsOnly();
      });
    } else {
      _demoRefreshTimer?.cancel();
      _demoRefreshTimer = null;
    }
  }

  @override
  void dispose() {
    _demoRefreshTimer?.cancel();
    _demoRefreshTimer = null;
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final auth = context.read<AuthController>();
      if (auth.isDemo) {
        final repo = DemoRepository.instance;
        repo.ensureInitialized();

        _missions = repo.listMissions().map((e) => MissionModel.fromJson(e)).toList();
        _vehicles = repo.listVehicles().map((e) => VehicleModel.fromJson(e)).toList();
        _fleets = repo.listFleets().map((e) => FleetModel.fromJson(e)).toList();
        setState(() {});
        return;
      }

      final api = context.read<ApiClient>();
      final missionsRes = await api.getJson('/missions');
      final vehiclesRes = await api.getJson('/fleet/vehicles', query: {'page': '1', 'page_size': '200'});
      final fleetsRes = await api.getJson('/fleet/fleets');

      if (missionsRes is List) {
        _missions = missionsRes
            .whereType<Map>()
            .map((e) => MissionModel.fromJson(e.cast<String, dynamic>()))
            .toList();
      }
      if (vehiclesRes is Map && vehiclesRes['items'] is List) {
        _vehicles = (vehiclesRes['items'] as List)
            .whereType<Map>()
            .map((e) => VehicleModel.fromJson(e.cast<String, dynamic>()))
            .toList();
      }
      if (fleetsRes is List) {
        _fleets = fleetsRes
            .whereType<Map>()
            .map((e) => FleetModel.fromJson(e.cast<String, dynamic>()))
            .toList();
      }
      setState(() {});
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _loadMissionsOnly() async {
    try {
      final api = context.read<ApiClient>();
      final missionsRes = await api.getJson('/missions');
      if (missionsRes is List) {
        final next = missionsRes
            .whereType<Map>()
            .map((e) => MissionModel.fromJson(e.cast<String, dynamic>()))
            .toList();
        if (!mounted) return;
        setState(() {
          _missions = next;
        });
      }
    } catch (_) {
      // Ignore demo refresh errors.
    }
  }

  Future<List<String>> _resolveTargetVehicleIds() async {
    if (_targetMode == 'vehicles') {
      return _selectedVehicleIds.toList();
    }
    final fleetId = _selectedFleetId;
    if (fleetId == null) return [];

    final auth = context.read<AuthController>();
    if (auth.isDemo) {
      final repo = DemoRepository.instance;
      repo.ensureInitialized();
      return repo
          .listVehicles(fleetId: fleetId)
          .map((e) => e['id']?.toString())
          .whereType<String>()
          .toList();
    }

    final api = context.read<ApiClient>();
    final vehiclesRes = await api.getJson('/fleet/vehicles', query: {'page': '1', 'page_size': '200', 'fleet_id': fleetId});
    if (vehiclesRes is Map && vehiclesRes['items'] is List) {
      return (vehiclesRes['items'] as List)
          .whereType<Map>()
          .map((e) => e['id']?.toString())
          .whereType<String>()
          .toList();
    }
    return [];
  }

  bool _hasAnyRole(AuthController auth, Set<String> roles) {
    return roles.contains(auth.role);
  }

  Future<void> _launch() async {
    final auth = context.read<AuthController>();
    final messenger = ScaffoldMessenger.of(context);
    final canAssign = _hasAnyRole(auth, {'operator', 'admin', 'super_admin'});
    final canPilot = _hasAnyRole(auth, {'pilot', 'admin', 'super_admin'});
    if (!canAssign && !canPilot) {
      messenger.showSnackBar(const SnackBar(content: Text('Insufficient permissions (need operator or pilot).')));
      return;
    }

    final missionIds = _selectedMissionIds.toList();
    if (missionIds.isEmpty) {
      messenger.showSnackBar(const SnackBar(content: Text('Select at least one mission.')));
      return;
    }

    setState(() => _assigning = true);
    try {
      final api = context.read<ApiClient>();
      final vehicleIds = await _resolveTargetVehicleIds();
      if (vehicleIds.isEmpty) {
        messenger.showSnackBar(const SnackBar(content: Text('Select vehicles or a fleet.')));
        return;
      }
      for (final mId in missionIds) {
        if (canAssign) {
          await api.postJson('/missions/$mId/assign', {
            'vehicle_ids': vehicleIds,
            'replace_existing': true,
          });
        }

        if (canPilot) {
          for (final vId in vehicleIds) {
            await api.postJson('/missions/upload', {
              'vehicle_id': vId,
              'mission_id': mId,
            });

            await api.postJson('/commands', {
              'vehicle_id': vId,
              'command': 'mission_start',
              'idempotency_key': _idempotencyKey(vId, mId),
              'params': {'mission_id': mId},
              'priority': 0,
              'timeout_seconds': 30,
            });
          }
        }
      }
      if (!mounted) return;
      if (canPilot) {
        messenger.showSnackBar(const SnackBar(content: Text('Launch requested (assign/upload/start).')));
      } else {
        messenger.showSnackBar(const SnackBar(content: Text('Mission(s) assigned.')));
      }
    } catch (e) {
      if (!mounted) return;
      messenger.showSnackBar(SnackBar(content: Text('Launch failed: $e')));
    } finally {
      setState(() => _assigning = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    final auth = context.watch<AuthController>();
    final scheme = Theme.of(context).colorScheme;

    final selectedMissionCount = _selectedMissionIds.length;
    final selectedVehicleCount = _selectedVehicleIds.length;
    final hasMissionSelection = selectedMissionCount > 0;
    final hasTargetSelection = _targetMode == 'fleet' ? (_selectedFleetId != null) : selectedVehicleCount > 0;
    final canPressLaunch = !_assigning && hasMissionSelection && hasTargetSelection;

    final targetSummary = _targetMode == 'fleet'
        ? (_selectedFleetId == null ? 'No fleet selected' : 'Fleet selected')
        : (selectedVehicleCount == 0 ? 'No vehicles selected' : '$selectedVehicleCount vehicle(s) selected');

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(_error!, style: TextStyle(color: scheme.error)),
            ),

          Text('Missions', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),

          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.rocket_launch),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text('Quick launch', style: Theme.of(context).textTheme.titleMedium),
                      ),
                      Text(
                        auth.role,
                        style: Theme.of(context).textTheme.labelMedium?.copyWith(color: scheme.onSurfaceVariant),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      Chip(
                        label: Text('$selectedMissionCount mission(s)'),
                        avatar: const Icon(Icons.flag, size: 18),
                      ),
                      Chip(
                        label: Text(targetSummary),
                        avatar: Icon(_targetMode == 'fleet' ? Icons.group_work : Icons.air, size: 18),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Select a mission, choose a target, then launch. Launch runs assign and/or start depending on your role.',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
          ),

          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text('1) Select mission(s)', style: Theme.of(context).textTheme.titleMedium),
                      ),
                      if (_selectedMissionIds.isNotEmpty)
                        TextButton(
                          onPressed: () => setState(() => _selectedMissionIds.clear()),
                          child: const Text('Clear'),
                        ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Pick one or more predefined missions.',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                  ),
                  const SizedBox(height: 8),
                  if (_missions.isEmpty)
                    Text(
                      auth.isDemo
                          ? 'Demo mode: showing demo missions only.'
                          : (auth.role == 'admin' || auth.role == 'super_admin')
                              ? 'No missions found.'
                              : 'No missions found. Missions must be assigned to your fleet/vehicles to appear here.',
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
                    )
                  else
                    ListView.separated(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: _missions.length,
                      separatorBuilder: (context, index) => Divider(height: 1, color: scheme.outlineVariant),
                      itemBuilder: (context, i) {
                        final m = _missions[i];
                        final selected = _selectedMissionIds.contains(m.id);
                        return CheckboxListTile(
                          contentPadding: const EdgeInsets.symmetric(horizontal: 4),
                          visualDensity: VisualDensity.compact,
                          value: selected,
                          onChanged: (v) {
                            setState(() {
                              if (v == true) {
                                _selectedMissionIds.add(m.id);
                              } else {
                                _selectedMissionIds.remove(m.id);
                              }
                            });
                          },
                          title: Text(m.name, maxLines: 1, overflow: TextOverflow.ellipsis),
                          subtitle: Text(
                            m.status,
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                          ),
                        );
                      },
                    ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('2) Choose target', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 6),
                  Text(
                    'Choose vehicles or a fleet for assignment/launch.',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                  ),
                  const SizedBox(height: 10),
                  SegmentedButton<String>(
                    segments: const [
                      ButtonSegment(value: 'vehicles', label: Text('Vehicles'), icon: DroneLogo(size: 18)),
                      ButtonSegment(value: 'fleet', label: Text('Fleet'), icon: Icon(Icons.group_work)),
                    ],
                    selected: {_targetMode},
                    onSelectionChanged: (s) {
                      setState(() {
                        _targetMode = s.first;
                        _selectedVehicleIds.clear();
                        _selectedFleetId = null;
                      });
                    },
                  ),
                  const SizedBox(height: 10),
                  if (_targetMode == 'fleet')
                    DropdownButtonFormField<String>(
                      key: ValueKey(_selectedFleetId ?? 'none'),
                      isExpanded: true,
                      initialValue: _selectedFleetId,
                      decoration: const InputDecoration(
                        labelText: 'Fleet',
                        prefixIcon: Icon(Icons.group_work),
                      ),
                      hint: const Text('Select a fleet'),
                      items: _fleets
                          .map((f) => DropdownMenuItem(value: f.id, child: Text('${f.name} (${f.onlineCount}/${f.vehicleCount} online)')))
                          .toList(),
                      onChanged: (id) => setState(() => _selectedFleetId = id),
                    )
                  else ...[
                    if (_vehicles.isEmpty)
                      Text('No vehicles found.', style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: scheme.onSurfaceVariant))
                    else
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              'Vehicles',
                              style: Theme.of(context).textTheme.labelLarge?.copyWith(color: scheme.onSurfaceVariant),
                            ),
                          ),
                          if (_selectedVehicleIds.isNotEmpty)
                            TextButton(
                              onPressed: () => setState(() => _selectedVehicleIds.clear()),
                              child: const Text('Clear'),
                            ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      ListView.separated(
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        itemCount: _vehicles.length,
                        separatorBuilder: (context, index) => Divider(height: 1, color: scheme.outlineVariant),
                        itemBuilder: (context, i) {
                          final v = _vehicles[i];
                          final selected = _selectedVehicleIds.contains(v.id);
                          return CheckboxListTile(
                            contentPadding: const EdgeInsets.symmetric(horizontal: 4),
                            visualDensity: VisualDensity.compact,
                            value: selected,
                            onChanged: (val) {
                              setState(() {
                                if (val == true) {
                                  _selectedVehicleIds.add(v.id);
                                } else {
                                  _selectedVehicleIds.remove(v.id);
                                }
                              });
                            },
                            title: Text(v.name, maxLines: 1, overflow: TextOverflow.ellipsis),
                            subtitle: Text(
                              v.status,
                              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                            ),
                          );
                        },
                      ),
                  ],
                  const SizedBox(height: 12),
                  Text('3) Launch', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: canPressLaunch ? _launch : null,
                      icon: const Icon(Icons.rocket_launch),
                      label: Text(_assigning ? 'Launching…' : 'Launch selected mission(s)'),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    (!hasMissionSelection)
                        ? 'Select at least one mission to enable launch.'
                        : (!hasTargetSelection)
                            ? 'Select a fleet or one or more vehicles to enable launch.'
                            : 'Ready to launch.',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

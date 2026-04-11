import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_map_marker_cluster/flutter_map_marker_cluster.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../../models/vehicle_model.dart';
import '../../realtime/realtime_controller.dart';
import '../screens/drone_details_screen.dart';
import '../widgets/drone_map_marker.dart';
import '../widgets/drone_map_styles.dart';

class FleetMapFullscreenScreen extends StatefulWidget {
  const FleetMapFullscreenScreen({
    super.key,
    required this.vehicles,
    required this.defaultCenter,
    required this.defaultZoom,
    required this.tileUrlTemplate,
    required this.tileSubdomains,
  });

  final List<VehicleModel> vehicles;
  final LatLng defaultCenter;
  final double defaultZoom;
  final String tileUrlTemplate;
  final List<String> tileSubdomains;

  @override
  State<FleetMapFullscreenScreen> createState() => _FleetMapFullscreenScreenState();
}

class _FleetMapFullscreenScreenState extends State<FleetMapFullscreenScreen> {
  final MapController _mapController = MapController();
  int _lastMarkerCount = -1;
  bool _userInteracted = false;

  String? _selectedVehicleId;
  bool _legendCollapsed = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _fitToMarkers());
  }

  List<_VehicleMarker> _markers(RealtimeController realtime) {
    final markers = <_VehicleMarker>[];
    for (final v in widget.vehicles) {
      final t = realtime.latestTelemetry[v.id];
      if (t == null) continue;
      if (t.lat == 0 || t.lng == 0) continue;

      final state = DroneMapStyle.stateFrom(status: v.status, armed: t.armed);
      markers.add(
        _VehicleMarker(
          vehicleId: v.id,
          name: v.name,
          vehicleType: v.type,
          state: state,
          headingDeg: t.heading,
          point: LatLng(t.lat, t.lng),
          altMeters: t.alt,
          speedMps: t.groundspeed,
        ),
      );
    }
    return markers;
  }

  void _fitToMarkers() {
    if (!mounted) return;
    final realtime = context.read<RealtimeController>();
    final markers = _markers(realtime);
    if (markers.isEmpty) return;

    _fitToMarkersList(markers);
  }

  void _fitToMarkersList(List<_VehicleMarker> markers) {
    if (markers.isEmpty) return;
    final bounds = LatLngBounds.fromPoints(markers.map((m) => m.point).toList());
    _mapController.fitCamera(
      CameraFit.bounds(
        bounds: bounds,
        padding: const EdgeInsets.all(48),
        maxZoom: 16,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final realtime = context.watch<RealtimeController>();
    final scheme = Theme.of(context).colorScheme;

    final markers = _markers(realtime);

    if (markers.isNotEmpty && markers.length != _lastMarkerCount) {
      _lastMarkerCount = markers.length;
      if (!_userInteracted) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted) return;
          _fitToMarkersList(markers);
        });
      }
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Map'),
      ),
      body: Stack(
        children: [
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: widget.defaultCenter,
              initialZoom: widget.defaultZoom,
              minZoom: 3,
              maxZoom: 22,
              onPositionChanged: (pos, hasGesture) {
                if (hasGesture) {
                  _userInteracted = true;
                }
              },
              onTap: (_, _) => setState(() => _selectedVehicleId = null),
            ),
            children: [
              TileLayer(
                urlTemplate: widget.tileUrlTemplate,
                subdomains: widget.tileSubdomains,
                userAgentPackageName: 'aerocommand_mobile',
              ),
              MarkerClusterLayerWidget(
                options: MarkerClusterLayerOptions(
                  markers: [
                    for (final m in markers)
                      Marker(
                        key: ValueKey('map-marker-${m.vehicleId}'),
                        point: m.point,
                        width: _selectedVehicleId == m.vehicleId ? 220 : 48,
                        height: 48,
                        child: DroneMapMarker(
                          key: ValueKey('drone-marker-${m.vehicleId}'),
                          vm: DroneMarkerViewModel(
                            vehicleId: m.vehicleId,
                            name: m.name,
                            vehicleType: m.vehicleType,
                            state: m.state,
                            headingDeg: m.headingDeg,
                            altMeters: m.altMeters,
                            speedMps: m.speedMps,
                          ),
                          selected: _selectedVehicleId == m.vehicleId,
                          showLabel: _selectedVehicleId == m.vehicleId,
                          onTap: () {
                            if (_selectedVehicleId != m.vehicleId) {
                              setState(() => _selectedVehicleId = m.vehicleId);
                              return;
                            }
                            Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) => DroneDetailsScreen(vehicleId: m.vehicleId, initialName: m.name),
                              ),
                            );
                          },
                        ),
                      ),
                  ],
                  maxClusterRadius: 44,
                  size: const Size(46, 46),
                  builder: (context, clusterMarkers) {
                    return DecoratedBox(
                      decoration: BoxDecoration(
                        color: scheme.surface.withValues(alpha: 0.92),
                        shape: BoxShape.circle,
                        border: Border.all(color: scheme.outlineVariant.withValues(alpha: 0.65)),
                        boxShadow: [
                          BoxShadow(
                            color: Theme.of(context).shadowColor.withValues(alpha: 0.35),
                            blurRadius: 10,
                            offset: const Offset(0, 3),
                          ),
                        ],
                      ),
                      child: Center(
                        child: Text(
                          clusterMarkers.length.toString(),
                          style: Theme.of(context).textTheme.labelLarge,
                        ),
                      ),
                    );
                  },
                ),
              ),
              if (markers.isNotEmpty)
                RichAttributionWidget(
                  alignment: AttributionAlignment.bottomRight,
                  attributions: [
                    TextSourceAttribution('© OpenStreetMap contributors'),
                    TextSourceAttribution('© CARTO'),
                  ],
                ),
            ],
          ),
          Positioned(
            left: 12,
            top: 12,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: scheme.surface.withValues(alpha: 0.92),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                child: Text(
                  markers.isEmpty ? 'Waiting for live GPS…' : 'Live positions: ${markers.length}',
                  style: Theme.of(context).textTheme.labelMedium,
                ),
              ),
            ),
          ),
          Positioned(
            left: 12,
            right: 12,
            bottom: 12,
            child: DroneStateLegend(
              collapsed: _legendCollapsed,
              onToggleCollapsed: () => setState(() => _legendCollapsed = !_legendCollapsed),
            ),
          ),
        ],
      ),
    );
  }
}

class _VehicleMarker {
  _VehicleMarker({
    required this.vehicleId,
    required this.name,
    required this.vehicleType,
    required this.state,
    required this.headingDeg,
    required this.point,
    required this.altMeters,
    required this.speedMps,
  });

  final String vehicleId;
  final String name;
  final String vehicleType;
  final DroneOperationalState state;
  final double headingDeg;
  final LatLng point;
  final double altMeters;
  final double speedMps;
}

import 'package:aerocommand_mobile/src/ui/widgets/drone_map_marker.dart';
import 'package:aerocommand_mobile/src/ui/widgets/drone_map_styles.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue)),
    home: Scaffold(body: Center(child: child)),
  );
}

void main() {
  testWidgets('Marker label visibility toggles', (tester) async {
    final vm = DroneMarkerViewModel(
      vehicleId: 'v1',
      name: 'Drone A',
      vehicleType: 'quadcopter',
      state: DroneOperationalState.armed,
      headingDeg: 90,
      altMeters: 12,
      speedMps: 3.4,
    );

    await tester.pumpWidget(
      _wrap(
        DroneMapMarker(
          vm: vm,
          selected: false,
          showLabel: false,
          onTap: () {},
        ),
      ),
    );

    expect(find.text('Drone A'), findsNothing);

    await tester.pumpWidget(
      _wrap(
        DroneMapMarker(
          vm: vm,
          selected: true,
          showLabel: true,
          onTap: () {},
        ),
      ),
    );

    // Selected markers show both an info bubble and a name label.
    expect(find.text('Drone A'), findsNWidgets(2));
  });

  testWidgets('Marker exposes a11y label', (tester) async {
    final semantics = tester.ensureSemantics();
    try {
      await tester.pumpWidget(
        _wrap(
          DroneMapMarker(
            vm: DroneMarkerViewModel(
              vehicleId: 'v2',
              name: 'Drone Bravo',
              vehicleType: 'quadcopter',
              state: DroneOperationalState.inflight,
              headingDeg: 0,
            ),
            selected: false,
            showLabel: false,
            onTap: () {},
          ),
        ),
      );

      expect(find.bySemanticsLabel('Drone Drone Bravo — inflight'), findsOneWidget);
    } finally {
      semantics.dispose();
    }
  });

  testWidgets('Legend renders and is accessible', (tester) async {
    final semantics = tester.ensureSemantics();
    try {
      await tester.pumpWidget(
        _wrap(
          DroneStateLegend(
            collapsed: false,
            onToggleCollapsed: () {},
          ),
        ),
      );

      expect(find.text('Legend'), findsOneWidget);
      expect(find.text('armed'), findsOneWidget);
      expect(find.text('disarmed'), findsOneWidget);
      expect(find.text('inflight'), findsOneWidget);
      expect(find.text('unknown'), findsNothing);

      expect(find.bySemanticsLabel('Drone state legend'), findsOneWidget);
    } finally {
      semantics.dispose();
    }
  });
}

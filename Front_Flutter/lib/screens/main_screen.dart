import 'package:flutter/material.dart';

import 'home_screen.dart';
import 'settings_screen.dart';

// notification_service에서 탭 이동 요청 시 사용
final pendingNavTab = ValueNotifier<int>(-1);

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _currentIndex = 0;

  @override
  void initState() {
    super.initState();
    pendingNavTab.addListener(_handlePendingNav);
  }

  @override
  void dispose() {
    pendingNavTab.removeListener(_handlePendingNav);
    super.dispose();
  }

  void _handlePendingNav() {
    if (pendingNavTab.value >= 0) {
      setState(() => _currentIndex = pendingNavTab.value);
      pendingNavTab.value = -1;
    }
  }

  final List<Widget> _screens = const [
    HomeScreen(),
    SettingsScreen(),
  ];

  final List<NavigationDestination> _destinations = const [
    NavigationDestination(
      icon: Icon(Icons.home_outlined),
      selectedIcon: Icon(Icons.home),
      label: '현황',
    ),
    NavigationDestination(
      icon: Icon(Icons.settings_outlined),
      selectedIcon: Icon(Icons.settings),
      label: '설정',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _currentIndex, children: _screens),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentIndex,
        onDestinationSelected: (index) => setState(() => _currentIndex = index),
        destinations: _destinations,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        height: 68,
      ),
    );
  }
}

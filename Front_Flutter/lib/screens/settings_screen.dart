import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/theme_provider.dart';
import 'login_screen.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('설정', style: TextStyle(fontWeight: FontWeight.w700)),
        centerTitle: false,
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _SectionHeader(label: '디스플레이'),
          Card(
            elevation: 0,
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            color: colorScheme.surfaceContainerLow,
            child: SwitchListTile(
              title: const Text('다크 모드',
                  style: TextStyle(fontWeight: FontWeight.w500)),
              subtitle: Text(themeProvider.isDark ? '어두운 테마 사용 중' : '밝은 테마 사용 중',
                  style: TextStyle(
                      fontSize: 12,
                      color: colorScheme.onSurface.withOpacity(0.55))),
              secondary: Icon(
                themeProvider.isDark
                    ? Icons.dark_mode_rounded
                    : Icons.light_mode_rounded,
                color: colorScheme.primary,
              ),
              value: themeProvider.isDark,
              onChanged: (_) => themeProvider.toggleTheme(),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16)),
            ),
          ),
          const SizedBox(height: 8),
          _SectionHeader(label: '앱 정보'),
          Card(
            elevation: 0,
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            color: colorScheme.surfaceContainerLow,
            child: Column(
              children: [
                ListTile(
                  leading: Icon(Icons.info_outline, color: colorScheme.primary),
                  title: const Text('버전',
                      style: TextStyle(fontWeight: FontWeight.w500)),
                  trailing: Text('1.0.0',
                      style: TextStyle(
                          color: colorScheme.onSurface.withOpacity(0.55))),
                  shape: const RoundedRectangleBorder(
                      borderRadius: BorderRadius.vertical(
                          top: Radius.circular(16))),
                ),
                Divider(
                    height: 1,
                    indent: 56,
                    color: colorScheme.outlineVariant.withOpacity(0.4)),
                ListTile(
                  leading:
                      Icon(Icons.kitchen_rounded, color: colorScheme.primary),
                  title: const Text('스마트 냉장고',
                      style: TextStyle(fontWeight: FontWeight.w500)),
                  trailing: Icon(Icons.chevron_right,
                      color: colorScheme.onSurface.withOpacity(0.3)),
                  shape: const RoundedRectangleBorder(
                      borderRadius: BorderRadius.vertical(
                          bottom: Radius.circular(16))),
                  onTap: () {},
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          _SectionHeader(label: '계정'),
          Card(
            elevation: 0,
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            color: colorScheme.surfaceContainerLow,
            child: ListTile(
              leading: const Icon(Icons.logout, color: Colors.red),
              title: const Text('로그아웃',
                  style: TextStyle(
                      fontWeight: FontWeight.w500, color: Colors.red)),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16)),
              onTap: () {
                Navigator.of(context).pushAndRemoveUntil(
                  MaterialPageRoute(builder: (_) => const LoginScreen()),
                  (_) => false,
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String label;
  const _SectionHeader({required this.label});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 12, 0, 6),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: Theme.of(context).colorScheme.primary,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}

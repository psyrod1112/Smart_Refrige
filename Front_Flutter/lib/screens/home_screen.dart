import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/food_item.dart';
import '../providers/food_provider.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<FoodProvider>().refresh();
    });
  }

  @override
  Widget build(BuildContext context) {
    final food = context.watch<FoodProvider>();
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text(
          '스마트 냉장고',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        actions: [
          IconButton(
            tooltip: '새로고침',
            icon: const Icon(Icons.refresh),
            onPressed: () => context.read<FoodProvider>().refresh(),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => context.read<FoodProvider>().refresh(),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            if (food.error != null) _ErrorBanner(message: food.error!),
            _StatusPanel(provider: food),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _SummaryCard(
                    icon: Icons.kitchen_rounded,
                    label: '보관 수량',
                    value: food.loading ? '-' : '${food.total}',
                    unit: '개',
                    color: colorScheme.primary,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _SummaryCard(
                    icon: Icons.warning_amber_rounded,
                    label: '유통기한 임박',
                    value: food.loading ? '-' : '${food.expiringSoon}',
                    unit: '개',
                    color: Colors.orange,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _SummaryCard(
                    icon: Icons.thermostat_rounded,
                    label: '온도',
                    value: food.temp?.toStringAsFixed(1) ?? '--',
                    unit: '°C',
                    color: Colors.teal,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _SummaryCard(
                    icon: Icons.water_drop_outlined,
                    label: '습도',
                    value: food.hum?.toStringAsFixed(1) ?? '--',
                    unit: '%',
                    color: Colors.indigo,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),
            Text(
              'FIFO 순서',
              style: Theme.of(
                context,
              ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            if (food.foods.isEmpty)
              const _EmptyActivity()
            else
              ...food.foods.take(5).map((item) => _RecentFoodTile(item: item)),
          ],
        ),
      ),
    );
  }
}

class _StatusPanel extends StatelessWidget {
  final FoodProvider provider;

  const _StatusPanel({required this.provider});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final hasPendingDetails = provider.pendingDetails.isNotEmpty;
    final needsConfirm = provider.slot.needsAppConfirm;
    final title = hasPendingDetails
        ? '새 식품 정보 입력 필요'
        : needsConfirm
        ? 'FIFO 확인 필요'
        : '정상 FIFO 상태';
    final body = hasPendingDetails
        ? '${provider.pendingDetails.length}개 식품의 이름과 유통기한을 확인해주세요.'
        : needsConfirm
        ? '앱에서 삭제 또는 수정 내용을 확인한 뒤 슬롯 상태를 해제하세요.'
        : '센서 감지와 DB 상태가 동기화되어 있습니다.';
    final color = hasPendingDetails || needsConfirm
        ? Colors.red
        : colorScheme.primary;

    return Card(
      elevation: 0,
      color: color.withValues(alpha: 0.08),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(
              hasPendingDetails || needsConfirm
                  ? Icons.notification_important
                  : Icons.check_circle,
              color: color,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(fontWeight: FontWeight.w700, color: color),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    body,
                    style: TextStyle(
                      fontSize: 12,
                      color: colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SummaryCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final String unit;
  final Color color;

  const _SummaryCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.unit,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      color: Theme.of(context).colorScheme.surfaceContainerLow,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color),
            const SizedBox(height: 10),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Flexible(
                  child: Text(
                    value,
                    style: TextStyle(
                      fontSize: 26,
                      fontWeight: FontWeight.w800,
                      color: color,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 3),
                Padding(
                  padding: const EdgeInsets.only(bottom: 3),
                  child: Text(
                    unit,
                    style: TextStyle(fontSize: 13, color: color),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 2),
            Text(label, style: const TextStyle(fontSize: 12)),
          ],
        ),
      ),
    );
  }
}

class _RecentFoodTile extends StatelessWidget {
  final FoodItem item;

  const _RecentFoodTile({required this.item});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final days = item.daysLeft;
    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      color: colorScheme.surfaceContainerLow,
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: colorScheme.primary.withValues(alpha: 0.12),
          child: Text(
            '${item.slotNumber}',
            style: TextStyle(color: colorScheme.primary),
          ),
        ),
        title: Text(item.displayName, overflow: TextOverflow.ellipsis),
        subtitle: Text(
          '${item.expiryDate} · ${item.quantity}개 · ${item.weightGram.toStringAsFixed(0)}g',
        ),
        trailing: Text(days < 0 ? '만료' : 'D-$days'),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  final String message;

  const _ErrorBanner({required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: Colors.red.shade50,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        '서버 연결 실패: $message',
        style: TextStyle(color: Colors.red.shade700),
      ),
    );
  }
}

class _EmptyActivity extends StatelessWidget {
  const _EmptyActivity();

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      color: Theme.of(context).colorScheme.surfaceContainerLow,
      child: const Padding(
        padding: EdgeInsets.symmetric(vertical: 36, horizontal: 20),
        child: Center(child: Text('등록된 식품이 없습니다.')),
      ),
    );
  }
}

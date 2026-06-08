import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/food_item.dart';
import '../providers/food_provider.dart';
import '../services/api_service.dart';

class IncomingFoodScreen extends StatefulWidget {
  const IncomingFoodScreen({super.key});

  @override
  State<IncomingFoodScreen> createState() => _IncomingFoodScreenState();
}

class _IncomingFoodScreenState extends State<IncomingFoodScreen> {
  bool _startingScan = false;

  @override
  void initState() {
    super.initState();
    Future.microtask(() => context.read<FoodProvider>().refresh());
  }

  Future<void> _startScan() async {
    setState(() => _startingScan = true);
    try {
      await startScan();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('OCR 스캔을 시작했습니다.')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('스캔 시작 실패: $e'), backgroundColor: Colors.red),
      );
    } finally {
      if (mounted) setState(() => _startingScan = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final food = context.watch<FoodProvider>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('입고상품', style: TextStyle(fontWeight: FontWeight.w700)),
        centerTitle: false,
        actions: [
          IconButton(
            tooltip: '스캔 시작',
            icon: _startingScan
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.document_scanner_outlined),
            onPressed: _startingScan ? null : _startScan,
          ),
          IconButton(
            tooltip: '새로고침',
            icon: const Icon(Icons.refresh),
            onPressed: () => context.read<FoodProvider>().refresh(),
          ),
        ],
      ),
      body: food.loading
          ? const Center(child: CircularProgressIndicator())
          : food.foods.isEmpty
              ? const _EmptyFoodList()
              : RefreshIndicator(
                  onRefresh: () => context.read<FoodProvider>().refresh(),
                  child: ListView.separated(
                    padding: const EdgeInsets.all(16),
                    itemCount: food.foods.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 8),
                    itemBuilder: (_, i) => _FoodCard(item: food.foods[i]),
                  ),
                ),
    );
  }
}

class _FoodCard extends StatelessWidget {
  final FoodItem item;

  const _FoodCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final days = item.daysLeft;
    final urgentColor = days <= 3
        ? Colors.red
        : days <= 7
            ? Colors.orange
            : colorScheme.primary;

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      color: colorScheme.surfaceContainerLow,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            CircleAvatar(
              radius: 22,
              backgroundColor: urgentColor.withOpacity(0.12),
              child: Text(
                '${item.slotNumber}',
                style: TextStyle(fontWeight: FontWeight.w700, color: urgentColor),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.foodTypeName,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${item.expiredDate} · ${item.storage} · ${item.weight.toStringAsFixed(0)}g',
                    style: TextStyle(
                      fontSize: 12,
                      color: colorScheme.onSurface.withOpacity(0.55),
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: urgentColor.withOpacity(0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                days < 0 ? '만료' : 'D-$days',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: urgentColor,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _EmptyFoodList extends StatelessWidget {
  const _EmptyFoodList();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.inventory_2_outlined,
            size: 72,
            color: Theme.of(context).colorScheme.onSurface.withOpacity(0.2),
          ),
          const SizedBox(height: 16),
          Text(
            '등록된 식품이 없습니다.',
            style: TextStyle(
              color: Theme.of(context).colorScheme.onSurface.withOpacity(0.4),
            ),
          ),
        ],
      ),
    );
  }
}

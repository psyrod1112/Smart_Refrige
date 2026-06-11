import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/food_item.dart';
import '../providers/food_provider.dart';

class ManualOutgoingScreen extends StatefulWidget {
  const ManualOutgoingScreen({super.key});

  @override
  State<ManualOutgoingScreen> createState() => _ManualOutgoingScreenState();
}

class _ManualOutgoingScreenState extends State<ManualOutgoingScreen> {
  FoodItem? _selected;
  String _reason = '소비';
  final List<String> _reasons = ['소비', '폐기', '이동'];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<FoodProvider>().refresh();
    });
  }

  Future<void> _submit() async {
    if (_selected == null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('출고할 식품을 선택해주세요.')));
      return;
    }
    try {
      final provider = context.read<FoodProvider>();
      await provider.outgo(_selected!.id, _reason);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${_selected!.displayName} 출고 확인 완료'),
          backgroundColor: Colors.orange,
        ),
      );
      setState(() => _selected = null);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('오류: $e'), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final food = context.watch<FoodProvider>();
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text(
          '출고 확인',
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
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Card(
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            color: colorScheme.surfaceContainerLow,
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                children: [
                  DropdownButtonFormField<FoodItem>(
                    initialValue: _selected,
                    decoration: const InputDecoration(
                      labelText: '출고할 식품',
                      prefixIcon: Icon(Icons.fastfood_outlined),
                      border: OutlineInputBorder(),
                    ),
                    hint: const Text('FIFO 순서에 맞는 식품 선택'),
                    items: food.foods
                        .map(
                          (f) => DropdownMenuItem(
                            value: f,
                            child: Text(
                              '${f.displayName} · ${f.expiryDate} · ${f.quantity}개',
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        )
                        .toList(),
                    onChanged: (v) => setState(() => _selected = v),
                  ),
                  const SizedBox(height: 14),
                  DropdownButtonFormField<String>(
                    initialValue: _reason,
                    decoration: const InputDecoration(
                      labelText: '출고 사유',
                      prefixIcon: Icon(Icons.move_up_outlined),
                      border: OutlineInputBorder(),
                    ),
                    items: _reasons
                        .map((r) => DropdownMenuItem(value: r, child: Text(r)))
                        .toList(),
                    onChanged: (v) => setState(() => _reason = v!),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          if (food.slot.needsAppConfirm)
            Card(
              elevation: 0,
              color: Colors.red.withValues(alpha: 0.08),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              child: const ListTile(
                leading: Icon(Icons.warning_amber_rounded, color: Colors.red),
                title: Text('FIFO 위반 확인 대기'),
                subtitle: Text('실제 제거된 식품을 선택해 출고 확인을 완료하세요.'),
              ),
            ),
          const SizedBox(height: 20),
          SizedBox(
            height: 52,
            child: FilledButton.icon(
              onPressed: food.loading ? null : _submit,
              icon: const Icon(Icons.move_up_outlined),
              label: const Text('출고 확인'),
            ),
          ),
        ],
      ),
    );
  }
}

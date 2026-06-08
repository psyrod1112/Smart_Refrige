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
    Future.microtask(() => context.read<FoodProvider>().refresh());
  }

  Future<void> _submit() async {
    if (_selected == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('출고할 식품을 선택해주세요.')),
      );
      return;
    }
    try {
      await context.read<FoodProvider>().outgo(_selected!.id, _reason);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${_selected!.foodTypeName} 출고 완료'),
          backgroundColor: Colors.orange,
        ),
      );
      setState(() => _selected = null);
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('오류: $e'), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final food = context.watch<FoodProvider>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('수동출고', style: TextStyle(fontWeight: FontWeight.w700)),
        centerTitle: false,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Card(
              elevation: 0,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              color: colorScheme.surfaceContainerLow,
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      '출고 정보',
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        color: colorScheme.onSurface,
                      ),
                    ),
                    const SizedBox(height: 20),
                    DropdownButtonFormField<FoodItem>(
                      value: _selected,
                      decoration: InputDecoration(
                        labelText: '출고할 식품',
                        prefixIcon: const Icon(Icons.fastfood_outlined),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                        filled: true,
                      ),
                      hint: const Text('식품 선택'),
                      items: food.foods
                          .map(
                            (f) => DropdownMenuItem(
                              value: f,
                              child: Text(
                                '${f.foodTypeName} · ${f.expiredDate} · 슬롯 ${f.slotNumber}',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          )
                          .toList(),
                      onChanged: (v) => setState(() => _selected = v),
                    ),
                    const SizedBox(height: 14),
                    DropdownButtonFormField<String>(
                      value: _reason,
                      decoration: InputDecoration(
                        labelText: '출고 사유',
                        prefixIcon: const Icon(Icons.move_up_outlined),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                        filled: true,
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
            const SizedBox(height: 20),
            SizedBox(
              height: 52,
              child: ElevatedButton.icon(
                onPressed: food.loading ? null : _submit,
                icon: const Icon(Icons.move_up_outlined),
                label: const Text(
                  '출고 처리',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orange,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

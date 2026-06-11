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
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<FoodProvider>().refresh();
    });
  }

  Future<void> _runAction(
    Future<void> Function() action,
    String message,
  ) async {
    setState(() => _busy = true);
    try {
      await action();
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('오류: $e'), backgroundColor: Colors.red),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _editFood(FoodItem item) async {
    final result = await showDialog<_FoodEditResult>(
      context: context,
      builder: (_) => _FoodEditDialog(item: item),
    );
    if (result == null || !mounted) return;

    await _runAction(
      () => context.read<FoodProvider>().saveInboundDetails(
        foodId: item.id,
        name: result.name,
        expiryDate: result.expiryDate,
        quantity: result.quantity,
      ),
      '식품 정보가 저장되었습니다.',
    );
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<FoodProvider>();
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text(
          '입고 관리',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        actions: [
          IconButton(
            tooltip: '스캔 시작',
            icon: const Icon(Icons.document_scanner_outlined),
            onPressed: _busy
                ? null
                : () => _runAction(startScan, 'OCR 스캔을 시작했습니다.'),
          ),
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
          padding: const EdgeInsets.all(16),
          children: [
            _ActionCard(
              title: '앱 접속 확인',
              body: '알림을 클릭했거나 OLED가 앱 접속을 요구하면 이 버튼으로 라즈베리파이에 접속 상태를 보냅니다.',
              icon: Icons.phone_iphone,
              color: colorScheme.primary,
              buttonLabel: '접속 확인',
              busy: _busy,
              onPressed: () => _runAction(
                () => context.read<FoodProvider>().markAppConnected(),
                '앱 접속 신호를 보냈습니다.',
              ),
            ),
            const SizedBox(height: 10),
            if (provider.slot.needsAppConfirm)
              _ActionCard(
                title: 'FIFO 확인 필요',
                body: '삭제 또는 수정할 내용을 확인한 뒤 슬롯 CONFIRM 상태를 해제합니다.',
                icon: Icons.rule_folder_outlined,
                color: Colors.red,
                buttonLabel: 'CONFIRM 해제',
                busy: _busy,
                onPressed: () => _runAction(
                  () => context.read<FoodProvider>().resolveConfirm(),
                  '슬롯 상태를 FIFO로 되돌렸습니다.',
                ),
              ),
            if (provider.slot.needsAppConfirm) const SizedBox(height: 10),
            Builder(
              builder: (context) => _ActionCard(
                title: '입고 앱 처리 완료',
                body: '식품명과 유통기한 입력을 마친 뒤 아두이노를 다음 입고 안내 단계로 넘깁니다.',
                icon: Icons.done_all,
                color: Colors.green,
                buttonLabel: '처리 완료',
                busy: _busy,
                onPressed: () {
                  final provider = context.read<FoodProvider>();
                  _runAction(() async {
                    await provider.completeInboundAppDone();
                  }, '입고 앱 처리를 완료했습니다.');
                },
              ),
            ),
            const SizedBox(height: 20),
            Text(
              'DB 식품 목록',
              style: Theme.of(
                context,
              ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            if (provider.loading)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(32),
                  child: CircularProgressIndicator(),
                ),
              )
            else if (provider.foods.isEmpty)
              const _EmptyFoodList()
            else
              ...provider.foods.map(
                (item) => _FoodCard(item: item, onTap: () => _editFood(item)),
              ),
          ],
        ),
      ),
    );
  }
}

class _ActionCard extends StatelessWidget {
  final String title;
  final String body;
  final IconData icon;
  final Color color;
  final String buttonLabel;
  final bool busy;
  final VoidCallback onPressed;

  const _ActionCard({
    required this.title,
    required this.body,
    required this.icon,
    required this.color,
    required this.buttonLabel,
    required this.busy,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      color: color.withValues(alpha: 0.08),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(icon, color: color),
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
                  Text(body, style: const TextStyle(fontSize: 12)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            FilledButton(
              onPressed: busy ? null : onPressed,
              child: Text(buttonLabel),
            ),
          ],
        ),
      ),
    );
  }
}

class _FoodCard extends StatelessWidget {
  final FoodItem item;
  final VoidCallback onTap;

  const _FoodCard({required this.item, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final days = item.daysLeft;
    final urgentColor = item.needsDetails
        ? Colors.red
        : days <= 3
        ? Colors.orange
        : Theme.of(context).colorScheme.primary;

    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      color: Theme.of(context).colorScheme.surfaceContainerLow,
      child: ListTile(
        onTap: onTap,
        leading: CircleAvatar(
          backgroundColor: urgentColor.withValues(alpha: 0.12),
          child: Text(
            '${item.slotNumber}',
            style: TextStyle(color: urgentColor),
          ),
        ),
        title: Text(item.displayName, overflow: TextOverflow.ellipsis),
        subtitle: Text(
          '${item.expiryDate} · ${item.quantity}개 · ${item.weightGram.toStringAsFixed(0)}g',
        ),
        trailing: item.needsDetails
            ? const Icon(Icons.edit_note, color: Colors.red)
            : Text(days < 0 ? '만료' : 'D-$days'),
      ),
    );
  }
}

class _FoodEditResult {
  final String name;
  final String expiryDate;
  final int quantity;

  const _FoodEditResult({
    required this.name,
    required this.expiryDate,
    required this.quantity,
  });
}

class _FoodEditDialog extends StatefulWidget {
  final FoodItem item;

  const _FoodEditDialog({required this.item});

  @override
  State<_FoodEditDialog> createState() => _FoodEditDialogState();
}

class _FoodEditDialogState extends State<_FoodEditDialog> {
  late final TextEditingController _nameController;
  late final TextEditingController _quantityController;
  DateTime? _expiryDate;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(
      text: widget.item.needsDetails ? '' : widget.item.name,
    );
    _quantityController = TextEditingController(
      text: '${widget.item.quantity}',
    );
    _expiryDate = DateTime.tryParse(widget.item.expiryDate);
  }

  @override
  void dispose() {
    _nameController.dispose();
    _quantityController.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _expiryDate ?? DateTime.now().add(const Duration(days: 7)),
      firstDate: DateTime(2020),
      lastDate: DateTime.now().add(const Duration(days: 365 * 5)),
    );
    if (picked != null) setState(() => _expiryDate = picked);
  }

  void _submit() {
    final name = _nameController.text.trim();
    final quantity = int.tryParse(_quantityController.text.trim()) ?? 0;
    if (name.isEmpty || _expiryDate == null || quantity <= 0) return;
    final expiry =
        '${_expiryDate!.year}-${_expiryDate!.month.toString().padLeft(2, '0')}-${_expiryDate!.day.toString().padLeft(2, '0')}';
    Navigator.of(
      context,
    ).pop(_FoodEditResult(name: name, expiryDate: expiry, quantity: quantity));
  }

  @override
  Widget build(BuildContext context) {
    final expiryLabel = _expiryDate == null
        ? '날짜 선택'
        : '${_expiryDate!.year}.${_expiryDate!.month.toString().padLeft(2, '0')}.${_expiryDate!.day.toString().padLeft(2, '0')}';

    return AlertDialog(
      title: const Text('식품 정보 입력'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _nameController,
            decoration: const InputDecoration(
              labelText: '식품명',
              prefixIcon: Icon(Icons.fastfood_outlined),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _quantityController,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              labelText: '수량',
              prefixIcon: Icon(Icons.numbers),
            ),
          ),
          const SizedBox(height: 12),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.calendar_today_outlined),
            title: Text(expiryLabel),
            onTap: _pickDate,
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('취소'),
        ),
        FilledButton(onPressed: _submit, child: const Text('저장')),
      ],
    );
  }
}

class _EmptyFoodList extends StatelessWidget {
  const _EmptyFoodList();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 48),
      child: Center(child: Text('등록된 식품이 없습니다.')),
    );
  }
}

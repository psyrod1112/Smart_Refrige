class SlotStatus {
  final int slotId;
  final String status;
  final double confirmDelta;
  final String confirmType;
  final double? baseWeightGram;
  final String? updatedAt;

  const SlotStatus({
    required this.slotId,
    required this.status,
    required this.confirmDelta,
    required this.confirmType,
    this.baseWeightGram,
    this.updatedAt,
  });

  factory SlotStatus.fromJson(Map<String, dynamic>? json) {
    final j = json ?? const <String, dynamic>{};
    return SlotStatus(
      slotId: (j['slot_id'] as num?)?.toInt() ?? 1,
      status: j['status'] as String? ?? 'FIFO',
      confirmDelta: (j['confirm_delta'] as num?)?.toDouble() ?? 0,
      confirmType: j['confirm_type'] as String? ?? 'OUTBOUND',
      baseWeightGram: (j['base_weight_gram'] as num?)?.toDouble(),
      updatedAt: j['updated_at'] as String?,
    );
  }

  bool get needsAppConfirm => status.toUpperCase() == 'CONFIRM';
}

class FoodItem {
  final int id;
  final String name;
  final String? foodType;
  final String expiryDate;
  final int quantity;
  final double weightGram;
  final int slotNumber;
  final String registeredAt;

  const FoodItem({
    required this.id,
    required this.name,
    this.foodType,
    required this.expiryDate,
    required this.quantity,
    required this.weightGram,
    required this.slotNumber,
    required this.registeredAt,
  });

  factory FoodItem.fromJson(Map<String, dynamic> json) {
    final weightValue = json['weight_gram'] ?? json['weight'];
    final slotValue = json['slot_id'] ?? json['slot_number'];
    return FoodItem(
      id: (json['id'] as num).toInt(),
      name: (json['name'] ?? json['food_type_name'] ?? '').toString(),
      foodType: json['food_type'] as String?,
      expiryDate: (json['expiry_date'] ?? json['expired_date'] ?? '')
          .toString(),
      quantity: (json['quantity'] as num?)?.toInt() ?? 1,
      weightGram: (weightValue as num?)?.toDouble() ?? 0,
      slotNumber: (slotValue as num?)?.toInt() ?? 1,
      registeredAt: (json['registered_at'] ?? json['created_at'] ?? '')
          .toString(),
    );
  }

  String get displayName => name.trim().isEmpty ? '이름 미등록' : name;
  String get foodTypeName => displayName;
  String get expiredDate => expiryDate;
  double get weight => weightGram;
  String get storage => '냉장';
  String get status => 'stored';
  String get createdAt => registeredAt;

  bool get needsDetails {
    final normalized = name.trim().toLowerCase();
    return normalized.isEmpty || normalized == 'unknown' || expiryDate.isEmpty;
  }

  int get daysLeft {
    final expiry = DateTime.tryParse(expiryDate);
    if (expiry == null) return 999;
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    return expiry.difference(today).inDays;
  }
}

class FoodItem {
  final int    id;
  final int?   foodTypeId;
  final String foodTypeName;
  final String expiredDate;
  final int    quantity;
  final double weight;
  final String storage;
  final int    slotNumber;
  final String status;
  final String createdAt;

  FoodItem({
    required this.id,
    this.foodTypeId,
    required this.foodTypeName,
    required this.expiredDate,
    required this.quantity,
    required this.weight,
    required this.storage,
    required this.slotNumber,
    required this.status,
    required this.createdAt,
  });

  factory FoodItem.fromJson(Map<String, dynamic> j) => FoodItem(
    id:           j['id']             as int,
    foodTypeId:   j['food_type_id']   as int?,
    foodTypeName: j['food_type_name'] as String? ?? '',
    expiredDate:  j['expired_date']   as String,
    quantity:     j['quantity']       as int? ?? 1,
    weight:       (j['weight'] as num?)?.toDouble() ?? 0,
    storage:      j['storage']        as String? ?? '냉장',
    slotNumber:   j['slot_number']    as int? ?? 0,
    status:       j['status']         as String? ?? 'stored',
    createdAt:    j['created_at']     as String? ?? '',
  );

  int get daysLeft {
    final expiry = DateTime.tryParse(expiredDate);
    if (expiry == null) return 999;
    return expiry.difference(DateTime.now()).inDays;
  }
}

import 'package:flutter/material.dart';

import '../models/food_item.dart';
import '../services/api_service.dart';

class FoodProvider extends ChangeNotifier {
  List<FoodItem> foods = [];
  SlotStatus slot = SlotStatus.fromJson(null);
  int total = 0;
  int expiringSoon = 0;
  double? temp;
  double? hum;
  bool loading = false;
  String? error;

  List<FoodItem> get pendingDetails =>
      foods.where((item) => item.needsDetails).toList();
  bool get needsAppConfirm => slot.needsAppConfirm || pendingDetails.isNotEmpty;

  Future<void> refresh() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      final payload = await fetchFoodsPayload();
      foods = payload.foods;
      slot = payload.slot;

      final dash = await fetchDashboard();
      total =
          (dash['total'] as num?)?.toInt() ??
          foods.fold<int>(0, (sum, item) => sum + item.quantity);
      expiringSoon =
          (dash['expiring_soon'] as num?)?.toInt() ??
          foods.where((item) => item.daysLeft <= 3).length;
      temp = (dash['temp'] as num?)?.toDouble();
      hum = (dash['hum'] as num?)?.toDouble();
      final slotJson = dash['slot'];
      if (slotJson is Map<String, dynamic>) {
        slot = SlotStatus.fromJson(slotJson);
      }
    } catch (e) {
      error = e.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> markAppConnected() async {
    slot = await notifyAppConnected();
    notifyListeners();
  }

  Future<void> addManual({
    required String expiredDate,
    required String storage,
    required String foodTypeName,
    int quantity = 1,
    double weight = 0,
  }) async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      await addFoodManual(
        expiredDate: expiredDate,
        storage: storage,
        foodTypeName: foodTypeName,
        quantity: quantity,
        weight: weight,
      );
      await refresh();
    } catch (e) {
      error = e.toString();
      loading = false;
      notifyListeners();
      rethrow;
    }
  }

  Future<void> saveInboundDetails({
    int? foodId,
    required String name,
    required String expiryDate,
    int quantity = 1,
  }) async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      await submitInboundDetails(
        foodId: foodId,
        name: name,
        expiryDate: expiryDate,
        quantity: quantity,
      );
      await refresh();
    } catch (e) {
      error = e.toString();
      loading = false;
      notifyListeners();
      rethrow;
    }
  }

  Future<void> updateDetails({
    required int id,
    String? name,
    String? expiryDate,
    int? quantity,
    double? weightGram,
  }) async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      await updateFood(
        id,
        name: name,
        expiryDate: expiryDate,
        quantity: quantity,
        weightGram: weightGram,
      );
      await refresh();
    } catch (e) {
      error = e.toString();
      loading = false;
      notifyListeners();
      rethrow;
    }
  }

  Future<void> outgo(int id, String reason) async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      await outgoFood(id);
      await refresh();
    } catch (e) {
      error = e.toString();
      loading = false;
      notifyListeners();
      rethrow;
    }
  }

  Future<void> resolveConfirm() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      slot = await resolveSlotConfirm();
      await refresh();
    } catch (e) {
      error = e.toString();
      loading = false;
      notifyListeners();
      rethrow;
    }
  }

  Future<int> completeInboundAppDone() async {
    final position = await completeInboundAppStep();
    await refresh();
    return position;
  }
}

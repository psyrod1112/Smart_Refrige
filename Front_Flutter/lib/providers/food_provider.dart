import 'package:flutter/material.dart';
import '../models/food_item.dart';
import '../services/api_service.dart';

class FoodProvider extends ChangeNotifier {
  List<FoodItem> foods        = [];
  int    total        = 0;
  int    expiringSoon = 0;
  double? temp;
  double? hum;
  bool   loading      = false;
  String? error;

  Future<void> refresh() async {
    loading = true;
    error   = null;
    notifyListeners();
    try {
      foods = await fetchFoods();
      final dash  = await fetchDashboard();
      total        = dash['total']        ?? 0;
      expiringSoon = dash['expiring_soon'] ?? 0;
      temp = (dash['temp'] as num?)?.toDouble();
      hum  = (dash['hum']  as num?)?.toDouble();
    } catch (e) {
      error = e.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> addManual({
    required String expiredDate,
    required String storage,
    required String foodTypeName,
    double weight = 0,
  }) async {
    await addFoodManual(
      expiredDate:   expiredDate,
      storage:       storage,
      foodTypeName:  foodTypeName,
      weight:        weight,
    );
    await refresh();
  }

  Future<void> outgo(int id, String reason) async {
    await outgoFood(id, reason);
    await refresh();
  }
}

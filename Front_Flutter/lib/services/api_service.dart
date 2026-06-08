import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/food_item.dart';

const String _baseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://192.168.137.97:5000',
);

Future<List<FoodItem>> fetchFoods() async {
  final res = await http.get(Uri.parse('$_baseUrl/foods'));
  if (res.statusCode != 200) {
    throw Exception('식품 목록 조회 실패');
  }
  final List list = jsonDecode(res.body);
  return list.map((e) => FoodItem.fromJson(e)).toList();
}

Future<void> addFoodManual({
  required String expiredDate,
  required String storage,
  required String foodTypeName,
  int quantity = 1,
  double weight = 0,
}) async {
  final res = await http.post(
    Uri.parse('$_baseUrl/foods'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({
      'expired_date': expiredDate,
      'storage': storage,
      'food_type_name': foodTypeName,
      'quantity': quantity,
      'weight': weight,
    }),
  );
  if (res.statusCode != 201) {
    throw Exception('수동 입고 실패');
  }
}

Future<void> outgoFood(int id, String reason) async {
  final statusMap = {'소비': 'consumed', '폐기': 'discarded', '이동': 'moved'};
  final res = await http.put(
    Uri.parse('$_baseUrl/foods/$id'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'status': statusMap[reason] ?? 'consumed'}),
  );
  if (res.statusCode != 200) {
    throw Exception('출고 실패');
  }
}

Future<Map<String, dynamic>> fetchDashboard() async {
  final res = await http.get(Uri.parse('$_baseUrl/dashboard'));
  if (res.statusCode != 200) {
    throw Exception('대시보드 조회 실패');
  }
  return jsonDecode(res.body);
}

Future<void> startScan() async {
  final res = await http.post(Uri.parse('$_baseUrl/scan/start'));
  if (res.statusCode != 200) {
    throw Exception('스캔 시작 실패');
  }
}

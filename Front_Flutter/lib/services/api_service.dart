import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/food_item.dart';

// ── 라즈베리파이 IP 주소 (같은 Wi-Fi 기준, 고정 IP 권장) ──────
const String _baseUrl = 'http://192.168.137.97:5000';

// ── 식품 목록 ──────────────────────────────────────────────────
Future<List<FoodItem>> fetchFoods() async {
  final res = await http.get(Uri.parse('$_baseUrl/foods'));
  if (res.statusCode != 200) throw Exception('foods 조회 실패');
  final List list = jsonDecode(res.body);
  return list.map((e) => FoodItem.fromJson(e)).toList();
}

// ── 수동 입고 ──────────────────────────────────────────────────
Future<void> addFoodManual({
  required String expiredDate,   // 'YYYY-MM-DD'
  required String storage,       // 냉장 / 냉동 / 상온
  required String foodTypeName,
  double weight = 0,
}) async {
  final res = await http.post(
    Uri.parse('$_baseUrl/foods'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({
      'expired_date':   expiredDate,
      'storage':        storage,
      'food_type_name': foodTypeName,
      'weight':         weight,
    }),
  );
  if (res.statusCode != 201) throw Exception('수동 입고 실패');
}

// ── 출고 처리 ──────────────────────────────────────────────────
Future<void> outgoFood(int id, String reason) async {
  final statusMap = {'소비': 'consumed', '폐기': 'discarded', '이동': 'moved'};
  final res = await http.put(
    Uri.parse('$_baseUrl/foods/$id'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'status': statusMap[reason] ?? 'consumed'}),
  );
  if (res.statusCode != 200) throw Exception('출고 실패');
}

// ── 홈 대시보드 ────────────────────────────────────────────────
Future<Map<String, dynamic>> fetchDashboard() async {
  final res = await http.get(Uri.parse('$_baseUrl/dashboard'));
  if (res.statusCode != 200) throw Exception('dashboard 조회 실패');
  return jsonDecode(res.body);
}

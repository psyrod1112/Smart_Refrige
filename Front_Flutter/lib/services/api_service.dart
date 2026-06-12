import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/food_item.dart';

const String baseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://192.168.137.97:5000',
);

class FoodsPayload {
  final SlotStatus slot;
  final List<FoodItem> foods;

  const FoodsPayload({required this.slot, required this.foods});
}

Uri _uri(String path, [Map<String, dynamic>? query]) {
  return Uri.parse('$baseUrl$path').replace(
    queryParameters: query?.map((key, value) => MapEntry(key, '$value')),
  );
}

Map<String, dynamic> _decodeMap(http.Response response) {
  final body = response.body.isEmpty ? '{}' : response.body;
  return jsonDecode(body) as Map<String, dynamic>;
}

Future<FoodsPayload> fetchFoodsPayload() async {
  final res = await http.get(_uri('/foods'));
  if (res.statusCode != 200) {
    throw Exception('식품 목록 조회 실패 (${res.statusCode})');
  }

  final decoded = jsonDecode(res.body);
  if (decoded is List) {
    return FoodsPayload(
      slot: SlotStatus.fromJson(null),
      foods: decoded
          .map((e) => FoodItem.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  final map = decoded as Map<String, dynamic>;
  final list = (map['foods'] as List? ?? const []);
  return FoodsPayload(
    slot: SlotStatus.fromJson(map['slot'] as Map<String, dynamic>?),
    foods: list
        .map((e) => FoodItem.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

Future<List<FoodItem>> fetchFoods() async {
  return (await fetchFoodsPayload()).foods;
}

Future<Map<String, dynamic>> fetchEnvironment() async {
  final res = await http.get(_uri('/environment'));
  if (res.statusCode != 200) {
    throw Exception('환경 데이터 조회 실패 (${res.statusCode})');
  }
  return _decodeMap(res);
}

Future<Map<String, dynamic>> fetchDashboard() async {
  final res = await http.get(_uri('/dashboard'));
  if (res.statusCode != 200) {
    throw Exception('대시보드 조회 실패 (${res.statusCode})');
  }
  return _decodeMap(res);
}

Future<List<Map<String, dynamic>>> fetchExpiringFoods({int days = 3}) async {
  final res = await http.get(_uri('/expiring', {'days': days}));
  if (res.statusCode != 200) {
    throw Exception('유통기한 임박 목록 조회 실패 (${res.statusCode})');
  }
  return (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
}

Future<void> registerFcmToken(String token) async {
  final res = await http.post(
    _uri('/fcm/token'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'token': token}),
  );
  if (res.statusCode >= 300) {
    throw Exception('FCM 토큰 등록 실패 (${res.statusCode})');
  }
}

Future<SlotStatus> notifyAppConnected() async {
  final res = await http.post(_uri('/app/connect'));
  if (res.statusCode != 200) {
    throw Exception('앱 접속 확인 실패 (${res.statusCode})');
  }
  return SlotStatus.fromJson(_decodeMap(res)['slot'] as Map<String, dynamic>?);
}

Future<void> startScan() async {
  final res = await http.post(_uri('/scan/start'));
  if (res.statusCode != 200) {
    throw Exception('스캔 시작 실패 (${res.statusCode})');
  }
}

Future<int?> addFoodManual({
  required String expiredDate,
  required String storage,
  required String foodTypeName,
  int quantity = 1,
  double weight = 0,
}) async {
  final res = await http.post(
    _uri('/foods'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({
      'name': foodTypeName,
      'expiry_date': expiredDate,
      'quantity': quantity,
      'weight_gram': weight,
    }),
  );
  if (res.statusCode != 201) {
    throw Exception('수동 입고 실패 (${res.statusCode})');
  }
  return (_decodeMap(res)['id'] as num?)?.toInt();
}

Future<void> submitInboundDetails({
  int? foodId,
  required String name,
  required String expiryDate,
  int quantity = 1,
}) async {
  final res = await http.post(
    _uri('/inbound/manual'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({
      if (foodId != null) 'food_id': foodId,
      'name': name,
      'expiry_date': expiryDate,
      'quantity': quantity,
    }),
  );
  if (res.statusCode >= 300) {
    throw Exception('입고 정보 저장 실패 (${res.statusCode})');
  }
}

Future<void> updateFood(
  int id, {
  String? name,
  String? expiryDate,
  int? quantity,
  double? weightGram,
}) async {
  final res = await http.patch(
    _uri('/foods/$id'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({
      if (name != null) 'name': name,
      if (expiryDate != null) 'expiry_date': expiryDate,
      if (quantity != null) 'quantity': quantity,
      if (weightGram != null) 'weight_gram': weightGram,
    }),
  );
  if (res.statusCode != 200) {
    throw Exception('식품 정보 수정 실패 (${res.statusCode})');
  }
}

Future<void> outgoFood(int id, {double delta = 0}) async {
  final res = await http.post(
    _uri('/outbound/confirm'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'food_id': id, 'delta': delta}),
  );
  if (res.statusCode != 200) {
    throw Exception('출고 확인 실패 (${res.statusCode})');
  }
}

Future<SlotStatus> resolveSlotConfirm() async {
  final res = await http.post(_uri('/slot/resolve'));
  if (res.statusCode != 200) {
    throw Exception('슬롯 상태 해제 실패 (${res.statusCode})');
  }
  return SlotStatus.fromJson(_decodeMap(res)['slot'] as Map<String, dynamic>?);
}

Future<int> completeInboundAppStep() async {
  final res = await http.post(_uri('/inbound/app_done'));
  if (res.statusCode != 200) {
    throw Exception('입고 앱 처리 완료 실패 (${res.statusCode})');
  }
  return (_decodeMap(res)['display_position'] as num?)?.toInt() ?? 1;
}

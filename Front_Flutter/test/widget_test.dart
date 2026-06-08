import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:smart_refrige/main.dart';
import 'package:smart_refrige/providers/food_provider.dart';
import 'package:smart_refrige/providers/theme_provider.dart';

void main() {
  testWidgets('login screen renders', (WidgetTester tester) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => ThemeProvider()),
          ChangeNotifierProvider(create: (_) => FoodProvider()),
        ],
        child: const SmartRefrigeApp(),
      ),
    );

    expect(find.text('스마트 냉장고'), findsWidgets);
    expect(find.text('로그인'), findsOneWidget);
  });
}

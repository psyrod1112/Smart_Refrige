import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import 'api_service.dart';
import '../screens/main_screen.dart';

const String notificationTopic = 'all_users';

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  try {
    await Firebase.initializeApp();
  } catch (_) {
    return;
  }
}

Future<void> initializePushNotifications() async {
  try {
    await Firebase.initializeApp();
    FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

    final messaging = FirebaseMessaging.instance;
    await messaging.requestPermission(alert: true, badge: true, sound: true);
    await messaging.subscribeToTopic(notificationTopic);

    final token = await messaging.getToken();
    if (token != null) {
      await registerFcmToken(token);
    }
    FirebaseMessaging.instance.onTokenRefresh.listen((token) {
      registerFcmToken(token).catchError((e) {
        // ignore: avoid_print
        print('[FCM] Token refresh registration failed: $e');
      });
    });

    FirebaseMessaging.onMessageOpenedApp.listen((_) async {
      try {
        await notifyAppConnected();
        pendingNavTab.value = 0; // 현황 탭으로 이동
      } catch (e) {
        // ignore: avoid_print
        print('[FCM] App connect callback failed: $e');
      }
    });

    final initialMessage = await messaging.getInitialMessage();
    if (initialMessage != null) {
      await notifyAppConnected();
      pendingNavTab.value = 1;
    }
  } catch (e) {
    // Firebase config files are device-specific and may be absent in local builds.
    // The app should still be usable without push notifications.
    // ignore: avoid_print
    print('[FCM] Push notifications disabled: $e');
  }
}

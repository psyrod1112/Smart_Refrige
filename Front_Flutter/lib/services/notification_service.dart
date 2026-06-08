import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

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
  } catch (e) {
    // Firebase config files are device-specific and may be absent in local builds.
    // The app should still be usable without push notifications.
    // ignore: avoid_print
    print('[FCM] Push notifications disabled: $e');
  }
}

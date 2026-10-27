import 'package:hive_flutter/hive_flutter.dart';

class LocalDB {
  static const String paymentsBoxName = 'offline_payments';
  static const String loansBoxName = 'offline_loans';

  static Future<void> init() async {
    await Hive.initFlutter();
    await Hive.openBox(paymentsBoxName);
    await Hive.openBox(loansBoxName);
  }

  // --- PAYMENT METHODS ---
  static Future<void> saveOfflinePayment(Map<String, dynamic> paymentData) async {
    final box = Hive.box(paymentsBoxName);
    await box.add({
      ...paymentData, 
      'synced': false, 
      'created_at': DateTime.now().toIso8601String()
    });
  }

  static List<Map<String, dynamic>> getUnsyncedPayments() {
    final box = Hive.box(paymentsBoxName);
    return box.keys
        .where((k) => box.get(k)['synced'] == false)
        .map((k) => {'key': k, ...Map<String, dynamic>.from(box.get(k))})
        .toList();
  }

  static Future<void> markAsSynced(dynamic key) async {
    final box = Hive.box(paymentsBoxName);
    final data = Map<String, dynamic>.from(box.get(key));
    data['synced'] = true;
    await box.put(key, data);
  }

  // --- LOAN METHODS ---
  static Future<void> saveLoans(List<Map<String, dynamic>> loans) async {
    final box = Hive.box(loansBoxName);
    await box.clear(); // We replace the whole cache on sync
    await box.addAll(loans);
  }

  static List<Map<String, dynamic>> getCachedLoans() {
    final box = Hive.box(loansBoxName);
    return box.values.map((e) => Map<String, dynamic>.from(e)).toList();
  }
}
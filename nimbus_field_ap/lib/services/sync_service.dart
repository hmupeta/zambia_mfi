import 'package:dio/dio.dart';
import 'api_client.dart';
import 'local_db.dart';

class SyncService {
  final ApiClient apiClient;
  SyncService(this.apiClient);

  Future<void> syncOfflinePayments() async {
    final unsyncedPayments = LocalDB.getUnsyncedPayments();
    if (unsyncedPayments.isEmpty) return;

    for (var payment in unsyncedPayments) {
      try {
        final paymentData = Map<String, dynamic>.from(payment);
        paymentData.remove('synced');
        paymentData.remove('created_at');
        final boxKey = paymentData.remove('key');

        // Send to your existing Django endpoint
        final response = await apiClient.dio.post('/payments/field-collections/', data: {
          'loan': paymentData['loan'],
          'amount': paymentData['amount'],
          'payment_method': paymentData['payment_method'],
          'transaction_ref': paymentData['transaction_ref'],
          'notes': paymentData['notes'],
        });

        if (response.statusCode == 201) {
          await LocalDB.markAsSynced(boxKey);
        }
      } on DioException catch (e) {
        // PRINT THE EXACT ERROR FROM DJANGO
        print('====== SYNC ERROR ======');
        print('Status: ${e.response?.statusCode}');
        print('Data: ${e.response?.data}');
        print('========================');

        // If it's a network error, break the loop and try again later
        if (e.type == DioExceptionType.connectionError || e.type == DioExceptionType.connectionTimeout) {
          break; 
        }
      }
    }
  }
}
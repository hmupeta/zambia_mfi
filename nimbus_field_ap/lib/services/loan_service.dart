import 'api_client.dart';
import 'local_db.dart';

class LoanService {
  final ApiClient apiClient;
  LoanService(this.apiClient);

  Future<void> syncLoansFromServer() async {
    try {
      // Fetching from your existing Django endpoint
      final response = await apiClient.dio.get('/loans/admin/?page_size=200');
      
      if (response.statusCode == 200) {
        // Handle Django pagination (results array)
        final List results = response.data['results'] ?? response.data;
        final List<Map<String, dynamic>> loans = List<Map<String, dynamic>>.from(results);
        await LocalDB.saveLoans(loans);
      }
    } catch (e) {
      // If network fails (offline), we just log it. The app will use the Hive cache.
      print('Failed to sync loans (likely offline): $e');
    }
  }
}
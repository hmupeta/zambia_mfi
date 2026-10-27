import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class CustomerApiClient {
  // Use your computer's IP (e.g., 192.168.x.x) if testing on a physical phone
  static const String baseUrl = 'http://localhost:8000/api'; 
  
  final Dio _dio = Dio(BaseOptions(baseUrl: baseUrl));
  final _storage = const FlutterSecureStorage();

  CustomerApiClient() {
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await _storage.read(key: 'access_token');
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        return handler.next(options);
      },
    ));
  }

  Future<bool> login(String phone, String password) async {
    try {
      // Uses the custom portal login endpoint we created in Django
      final response = await _dio.post('/portal/login/', data: {
        'phone': phone,
        'password': password,
      });
      
      if (response.statusCode == 200) {
        await _storage.write(key: 'access_token', value: response.data['access']);
        return true;
      }
      return false;
    } on DioException catch (e) {
      print('Login Error: ${e.response?.data ?? e.message}');
      return false;
    }
  }

  Future<List<dynamic>> getMyLoans() async {
    try {
      // Correct path including '/origination/'
      final response = await _dio.get('/origination/customer/loans/');
      
      // Handle both paginated and non-paginated responses
      return response.data is Map ? response.data['results'] : response.data;
    } on DioException catch (e) {
      print('Fetch Loans Error: ${e.response?.data ?? e.message}');
      return [];
    }
  }

  Future<List<dynamic>> getLoanProducts() async {
    try {
      // This matches the router.register(r'customer/products', ...)
      final response = await _dio.get('/origination/customer/products/'); 
      return response.data is Map ? response.data['results'] : response.data;
    } on DioException catch (e) {
      print('Fetch Products Error: ${e.response?.data ?? e.message}');
      return [];
    }
  }

  Future<bool> applyForLoan(Map<String, dynamic> data) async {
    try {
      // This matches path('customer/apply/', ...)
      final response = await _dio.post('/origination/customer/apply/', data: data);
      return response.statusCode == 201;
    } on DioException catch (e) {
      print('Apply Loan Error: ${e.response?.data ?? e.message}');
      return false;
    }
  }

  Future<void> logout() async {
    await _storage.deleteAll();
  }
}
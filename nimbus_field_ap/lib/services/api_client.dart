import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'user_session.dart';

class ApiClient {
  static const String baseUrl = 'http://localhost:8000/api'; 
  
  final Dio _dio = Dio(BaseOptions(
    baseUrl: baseUrl,
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 10),
  ));
  
  final _storage = const FlutterSecureStorage();

  ApiClient() {
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

  Dio get dio => _dio;

  Future<bool> login(String username, String password) async {
    try {
      final response = await _dio.post(
        '/auth/token/', 
        data: {'username': username, 'password': password},
      );

      if (response.statusCode == 200) {
        final data = response.data;
        if (data.containsKey('access')) {
          await _storage.write(key: 'access_token', value: data['access']);
        }
        if (data.containsKey('refresh')) {
          await _storage.write(key: 'refresh_token', value: data['refresh']);
        }
        await _fetchUserProfile(username);
        return true;
      }
      return false;
    } on DioException catch (e) {
      print('Login Error: ${e.response?.data ?? e.message}');
      return false;
    } catch (e) {
      print('Login Exception: $e');
      return false;
    }
  }

  Future<void> _fetchUserProfile(String username) async {
    try {
      final res = await _dio.get('/auth/');
      if (res.statusCode == 200) {
        final data = res.data;
        UserSession.organizationName = data['organization_name'] ?? 'Nimbus Microfinance';
        String rawBranch = data['branch_name']?.toString() ?? data['branch']?.toString() ?? 'Ndola Branch';
        UserSession.branchName = UserSession.getFriendlyBranchName(rawBranch);
        UserSession.officerName = data['full_name'] ?? data['first_name'] ?? username;
      }
    } catch (e) {
      print('Could not fetch user profile: $e');
      UserSession.officerName = username; 
    }
  }

  Future<void> logout() async {
    await _storage.deleteAll();
    UserSession.organizationName = 'Nimbus Microfinance';
    UserSession.branchName = 'Ndola Branch';
    UserSession.officerName = 'Field Officer';
  }

  Future<List<Map<String, dynamic>>> getLoanProducts() async {
    try {
      await Future.delayed(const Duration(milliseconds: 800)); 
      return [
        {'code': 'ACME_PAYDAY_01', 'name': 'Pay Day Loan'},
        {'code': 'AGRI', 'name': 'Agricultural Loan'},
        {'code': 'EMERG', 'name': 'Emergency Loan'},
        {'code': 'SME', 'name': 'Small Business Loan'},
      ];
    } catch (e) {
      print('Error fetching loan products: $e');
      return [];
    }
  }

  // --- NEW METHOD FOR FETCHING CLIENTS ---
  Future<List<Map<String, dynamic>>> getClients() async {
    try {
      final response = await _dio.get('/clients/?page_size=500');
      if (response.statusCode == 200) {
        final List results = response.data is Map ? (response.data['results'] ?? []) : response.data;
        return List<Map<String, dynamic>>.from(results);
      }
      return [];
    } catch (e) {
      print('Error fetching clients: $e');
      return [];
    }
  }
}
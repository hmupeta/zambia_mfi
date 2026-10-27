import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

void main() {
  runApp(
    MultiProvider(
      providers: [
        Provider(create: (_) => CustomerApiClient()),
      ],
      child: const CustomerApp(),
    ),
  );
}

class CustomerApp extends StatelessWidget {
  const CustomerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Nimbus Customer Portal',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.orange),
        useMaterial3: true,
      ),
      home: const CustomerLoginScreen(),
    );
  }
}

// ==========================================
// API CLIENT FOR CUSTOMERS
// ==========================================
class CustomerApiClient {
  static const String baseUrl = 'http://localhost:8000/api'; 
  
  final Dio _dio = Dio(BaseOptions(baseUrl: baseUrl));
  final _storage = const FlutterSecureStorage();

  CustomerApiClient() {
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        if (!options.path.contains('/portal/login/')) {
          final token = await _storage.read(key: 'access_token');
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
        }
        return handler.next(options);
      },
    ));
  }

  Future<bool> login(String phone, String password) async {
    try {
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
      final response = await _dio.get('/origination/customer/loans/');
      return response.data is Map ? response.data['results'] : response.data;
    } on DioException catch (e) {
      print('Fetch Loans Error: ${e.response?.data ?? e.message}');
      return [];
    }
  }

  Future<List<dynamic>> getLoanProducts() async {
    try {
      final response = await _dio.get('/origination/customer/products/'); 
      return response.data is Map ? response.data['results'] : response.data;
    } on DioException catch (e) {
      print('Fetch Products Error: ${e.response?.data ?? e.message}');
      return [];
    }
  }

  Future<bool> applyForLoan(Map<String, dynamic> data) async {
    try {
      final response = await _dio.post('/origination/customer/apply/', data: data);
      return response.statusCode == 201;
    } on DioException catch (e) {
      print('Apply Loan Error: ${e.response?.data ?? e.message}');
      return false;
    }
  }

  Future<Map<String, dynamic>?> initiateMtnPayment(String loanId, String amount, String phone) async {
    try {
      final response = await _dio.post('/momo/portal/mtn-pay/', data: {
        'loan_id': loanId,
        'amount': amount,
        'phone': phone,
      });
      return response.data;
    } on DioException catch (e) {
      print('MTN Pay Error: ${e.response?.data ?? e.message}');
      return null;
    }
  }

  Future<String> checkMtnPaymentStatus(String referenceId) async {
    try {
      final response = await _dio.get('/momo/portal/mtn-status/$referenceId/');
      return response.data['status'] ?? 'UNKNOWN';
    } on DioException catch (e) {
      print('Status Check Error: ${e.response?.data ?? e.message}');
      return 'ERROR';
    }
  }

  Future<void> logout() async {
    await _storage.deleteAll();
  }
}

// ==========================================
// LOGIN SCREEN
// ==========================================
class CustomerLoginScreen extends StatefulWidget {
  const CustomerLoginScreen({super.key});
  @override
  State<CustomerLoginScreen> createState() => _CustomerLoginScreenState();
}

class _CustomerLoginScreenState extends State<CustomerLoginScreen> {
  final _userController = TextEditingController();
  final _passController = TextEditingController();
  bool _isLoading = false;

  void _login() async {
    if (_userController.text.isEmpty || _passController.text.isEmpty) return;
    setState(() => _isLoading = true);
    
    final api = context.read<CustomerApiClient>();
    final success = await api.login(_userController.text.trim(), _passController.text);
    
    setState(() => _isLoading = false);

    if (success && mounted) {
      Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const CustomerDashboard()));
    } else if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Invalid credentials'), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.account_balance_wallet, size: 80, color: Colors.orange),
              const SizedBox(height: 20),
              const Text('Nimbus Customer Portal', style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
              const SizedBox(height: 40),
              TextField(
                controller: _userController,
                decoration: const InputDecoration(labelText: 'Phone Number / Username', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _passController,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'Password', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton(
                  onPressed: _isLoading ? null : _login,
                  child: _isLoading ? const CircularProgressIndicator() : const Text('Log In'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ==========================================
// DASHBOARD SCREEN
// ==========================================
class CustomerDashboard extends StatefulWidget {
  const CustomerDashboard({super.key});
  @override
  State<CustomerDashboard> createState() => _CustomerDashboardState();
}

class _CustomerDashboardState extends State<CustomerDashboard> {
  List<dynamic> _allLoans = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  void _loadData() async {
    final api = context.read<CustomerApiClient>();
    final loans = await api.getMyLoans();
    if (mounted) {
      setState(() {
        _allLoans = loans;
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final activeLoans = _allLoans.where((l) {
      final bal = double.tryParse(l['balance_due']?.toString() ?? '0') ?? 0.0;
      final status = l['status']?.toString().toUpperCase() ?? '';
      return bal > 0 && status != 'CLOSED' && status != 'COMPLETED';
    }).toList();

    final completedLoans = _allLoans.where((l) {
      final bal = double.tryParse(l['balance_due']?.toString() ?? '0') ?? 0.0;
      final status = l['status']?.toString().toUpperCase() ?? '';
      return bal <= 0 || status == 'CLOSED' || status == 'COMPLETED';
    }).toList();

    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('My Loans'),
          actions: [
            IconButton(
              icon: const Icon(Icons.logout),
              onPressed: () async {
                await context.read<CustomerApiClient>().logout();
                if (context.mounted) {
                  Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const CustomerLoginScreen()));
                }
              },
            )
          ],
          bottom: const TabBar(
            tabs: [ Tab(text: 'Active Loans'), Tab(text: 'Completed') ],
          ),
        ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: () async {
            await Navigator.push(context, MaterialPageRoute(builder: (_) => const NewLoanApplicationScreen()));
            _loadData();
          },
          icon: const Icon(Icons.add),
          label: const Text('Apply for Loan'),
          backgroundColor: Colors.orange,
        ),
        body: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : TabBarView(
                children: [
                  _buildLoanList(activeLoans, isActive: true),
                  _buildLoanList(completedLoans, isActive: false),
                ],
              ),
      ),
    );
  }

  Widget _buildLoanList(List<dynamic> loans, {required bool isActive}) {
    if (loans.isEmpty) {
      return Center(child: Text(isActive ? 'You have no active loans.' : 'You have no completed loans.', style: const TextStyle(color: Colors.grey)));
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: loans.length,
      itemBuilder: (context, index) {
        final loan = loans[index];
        final balance = double.tryParse(loan['balance_due']?.toString() ?? '0') ?? 0.0;

        return Card(
          margin: const EdgeInsets.only(bottom: 16),
          elevation: 2,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          child: InkWell(
            borderRadius: BorderRadius.circular(12),
            onTap: () {
              Navigator.push(context, MaterialPageRoute(builder: (_) => CustomerLoanDetailsScreen(loan: loan)))
                  .then((_) => _loadData());
            },
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    loan['organization_name'] ?? 'Nimbus MFI', 
                    style: TextStyle(color: Colors.blue.shade700, fontWeight: FontWeight.bold, fontSize: 12)
                  ),
                  const SizedBox(height: 4),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(loan['loan_number'] ?? 'Loan', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: isActive ? Colors.green.shade100 : Colors.grey.shade200,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(isActive ? 'ACTIVE' : 'COMPLETED', style: TextStyle(fontSize: 12, color: isActive ? Colors.green.shade800 : Colors.grey.shade700)),
                      ),
                    ],
                  ),
                  const Divider(),
                  Text(
                    isActive ? 'Outstanding Balance: K${balance.toStringAsFixed(2)}' : 'Loan Fully Paid', 
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: isActive ? Colors.red : Colors.green)
                  ),
                  const SizedBox(height: 8),
                  Text('Status: ${loan['is_fully_repaid'] == true ? 'Fully Paid' : 'Active'}'),
                  const SizedBox(height: 16),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('View Details & History', style: TextStyle(color: Colors.orange.shade800, fontWeight: FontWeight.w500)),
                      Icon(Icons.chevron_right, color: Colors.orange.shade800),
                    ],
                  )
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

// ==========================================
// NEW LOAN APPLICATION SCREEN
// ==========================================
class NewLoanApplicationScreen extends StatefulWidget {
  const NewLoanApplicationScreen({super.key});

  @override
  State<NewLoanApplicationScreen> createState() => _NewLoanApplicationScreenState();
}

class _NewLoanApplicationScreenState extends State<NewLoanApplicationScreen> {
  final _formKey = GlobalKey<FormState>();
  bool _isLoading = true;
  bool _isSaving = false;
  List<dynamic> _products = [];
  
  String? _selectedProductId;
  final _amountController = TextEditingController();
  final _tenureController = TextEditingController(text: '12');
  String _frequency = 'MONTHLY';
  String _purpose = 'BUSINESS_CAPITAL';
  final _notesController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadProducts();
  }

  void _loadProducts() async {
    final api = context.read<CustomerApiClient>();
    final products = await api.getLoanProducts();
    if (mounted) {
      setState(() {
        _products = products;
        _isLoading = false;
        if (products.isNotEmpty) _selectedProductId = products.first['id'].toString();
      });
    }
  }

  void _submitApplication() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _isSaving = true);

    final api = context.read<CustomerApiClient>();
    final success = await api.applyForLoan({
      'loan_product': _selectedProductId,
      'requested_amount': _amountController.text,
      'requested_tenure_months': _tenureController.text,
      'requested_repayment_frequency': _frequency,
      'purpose': _purpose,
      'purpose_notes': _notesController.text,
    });

    setState(() => _isSaving = false);

    if (success && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Application submitted! A Loan Officer will review it shortly.'), backgroundColor: Colors.green),
      );
      Navigator.pop(context);
    } else if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Failed to submit application. Please check your details and try again.'), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Apply for a Loan')),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : Form(
              key: _formKey,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  DropdownButtonFormField<String>(
                    value: _selectedProductId,
                    decoration: const InputDecoration(labelText: 'Loan Product', border: OutlineInputBorder()),
                    items: _products.map<DropdownMenuItem<String>>((p) {
                      return DropdownMenuItem<String>(
                        value: p['id'].toString(),
                        child: Text('${p['code']} — ${p['name']}'),
                      );
                    }).toList(),
                    onChanged: (v) => setState(() => _selectedProductId = v),
                    validator: (v) => v == null ? 'Required' : null,
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _amountController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Amount (ZMW)', border: OutlineInputBorder()),
                    validator: (v) => v!.isEmpty ? 'Required' : null,
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _tenureController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Tenure (Months)', border: OutlineInputBorder()),
                    validator: (v) => v!.isEmpty ? 'Required' : null,
                  ),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    value: _frequency,
                    decoration: const InputDecoration(labelText: 'Repayment Frequency', border: OutlineInputBorder()),
                    items: ['MONTHLY', 'BIWEEKLY', 'WEEKLY'].map((f) => DropdownMenuItem(value: f, child: Text(f))).toList(),
                    onChanged: (v) => setState(() => _frequency = v!),
                  ),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    value: _purpose,
                    decoration: const InputDecoration(labelText: 'Purpose', border: OutlineInputBorder()),
                    items: ['BUSINESS_CAPITAL', 'EQUIPMENT', 'EDUCATION', 'EMERGENCY'].map((p) => DropdownMenuItem(value: p, child: Text(p))).toList(),
                    onChanged: (v) => setState(() => _purpose = v!),
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _notesController,
                    maxLines: 3,
                    decoration: const InputDecoration(labelText: 'Purpose Notes (Optional)', border: OutlineInputBorder()),
                  ),
                  const SizedBox(height: 32),
                  SizedBox(
                    height: 50,
                    child: ElevatedButton(
                      onPressed: _isSaving ? null : _submitApplication,
                      child: _isSaving
                          ? const CircularProgressIndicator(color: Colors.white)
                          : const Text('Submit Application', style: TextStyle(fontSize: 16)),
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}

// ==========================================
// LOAN DETAILS & PAYMENT HISTORY SCREEN
// ==========================================
class CustomerLoanDetailsScreen extends StatefulWidget {
  final Map<String, dynamic> loan;
  const CustomerLoanDetailsScreen({super.key, required this.loan});

  @override
  State<CustomerLoanDetailsScreen> createState() => _CustomerLoanDetailsScreenState();
}

class _CustomerLoanDetailsScreenState extends State<CustomerLoanDetailsScreen> {
  Timer? _pollTimer;

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  void _makePayment() {
    final amountController = TextEditingController();
    final phoneController = TextEditingController();
    bool isProcessing = false;
    String statusMessage = '';

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (modalContext) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            return Padding(
              padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom, left: 16, right: 16, top: 24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('Pay via MTN MoMo', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  Text('Outstanding Balance: K${widget.loan['balance_due']}', style: const TextStyle(color: Colors.red, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 16),
                  
                  if (statusMessage.isNotEmpty) ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: statusMessage.contains('prompt') ? Colors.blue.shade50 : Colors.orange.shade50,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        statusMessage,
                        style: TextStyle(color: statusMessage.contains('prompt') ? Colors.blue.shade900 : Colors.orange.shade900),
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],

                  TextField(
                    controller: amountController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Amount (ZMW)', border: OutlineInputBorder()),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: phoneController,
                    keyboardType: TextInputType.phone,
                    decoration: const InputDecoration(labelText: 'MTN Phone Number (e.g. 0971234567)', border: OutlineInputBorder()),
                  ),
                  const SizedBox(height: 24),
                  SizedBox(
                    height: 50,
                    child: ElevatedButton(
                      onPressed: isProcessing || statusMessage.contains('prompt') ? null : () async {
                        if (amountController.text.isEmpty || phoneController.text.isEmpty) return;
                        
                        setModalState(() {
                          isProcessing = true;
                          statusMessage = '';
                        });

                        final api = context.read<CustomerApiClient>();
                        
                        final response = await api.initiateMtnPayment(
                          widget.loan['id'].toString(),
                          amountController.text,
                          phoneController.text,
                        );

                        if (response == null || response['ok'] != true) {
                          if (modalContext.mounted) {
                            setModalState(() {
                              isProcessing = false;
                              statusMessage = 'Failed to initiate payment. Check your phone number.';
                            });
                          }
                          return;
                        }

                        final refId = response['reference_id'];
                        if (modalContext.mounted) {
                          setModalState(() {
                            statusMessage = 'Payment prompt sent! Please check your phone and enter your PIN.';
                          });
                        }

                        _pollTimer?.cancel();
                        _pollTimer = Timer.periodic(const Duration(seconds: 5), (timer) async {
                          final status = await api.checkMtnPaymentStatus(refId);
                          
                          if (status == 'SUCCESSFUL') {
                            timer.cancel();
                            if (modalContext.mounted) {
                              Navigator.pop(modalContext);
                              if (mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(content: Text('Payment Successful!'), backgroundColor: Colors.green),
                                );
                              }
                            }
                          } else if (status == 'FAILED') {
                            timer.cancel();
                            if (modalContext.mounted) {
                              setModalState(() {
                                isProcessing = false;
                                statusMessage = 'Payment failed or was declined.';
                              });
                            }
                          }
                        });

                        Future.delayed(const Duration(minutes: 2), () {
                          _pollTimer?.cancel();
                          if (modalContext.mounted && statusMessage.contains('prompt')) {
                            setModalState(() {
                              isProcessing = false;
                              statusMessage = 'Payment request timed out. Please try again.';
                            });
                          }
                        });
                      },
                      child: isProcessing 
                        ? const CircularProgressIndicator(color: Colors.white) 
                        : const Text('Pay Now', style: TextStyle(fontSize: 16)),
                    ),
                  ),
                  const SizedBox(height: 24),
                ],
              ),
            );
          }
        );
      },
    ).then((_) {
      _pollTimer?.cancel();
    });
  }
  
  @override
  Widget build(BuildContext context) {
    final loan = widget.loan;
    final balance = double.tryParse(loan['balance_due']?.toString() ?? '0') ?? 0.0;
    final isActive = balance > 0 && loan['status'] != 'CLOSED';
    final payments = loan['payments'] as List<dynamic>? ?? [];

    return Scaffold(
      appBar: AppBar(title: Text('Loan ${loan['loan_number']}')),
      body: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Card(
                elevation: 0,
                color: isActive ? Colors.blue.shade50 : Colors.green.shade50,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: BorderSide(color: isActive ? Colors.blue.shade200 : Colors.green.shade200),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        loan['organization_name'] ?? 'Nimbus MFI',
                        style: TextStyle(color: Colors.blue.shade900, fontWeight: FontWeight.bold, fontSize: 12)
                      ),
                      const SizedBox(height: 4),
                      Text(isActive ? 'Active Loan' : 'Completed Loan', style: TextStyle(color: isActive ? Colors.blue.shade800 : Colors.green.shade800, fontWeight: FontWeight.bold)),
                      const SizedBox(height: 12),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text('Outstanding Balance', style: TextStyle(fontWeight: FontWeight.w500)),
                          Text('K ${balance.toStringAsFixed(2)}', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: isActive ? Colors.red : Colors.green)),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text('Status', style: TextStyle(fontWeight: FontWeight.w500)),
                          Text(loan['is_fully_repaid'] == true ? 'Fully Paid' : 'Active'),
                        ],
                      ),
                      if (isActive) ...[
                        const SizedBox(height: 16),
                        SizedBox(
                          width: double.infinity,
                          height: 45,
                          child: ElevatedButton.icon(
                            onPressed: _makePayment,
                            icon: const Icon(Icons.payment),
                            label: const Text('Make a Payment'),
                          ),
                        ),
                      ]
                    ],
                  ),
                ),
              ),
              
              const SizedBox(height: 24),
              const Text('Payment History', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 12),

              payments.isEmpty
                  ? const Center(
                      child: Padding(
                        padding: EdgeInsets.all(24.0),
                        child: Text('No payments have been made on this loan yet.', style: TextStyle(color: Colors.grey)),
                      ),
                    )
                  : ListView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: payments.length,
                      itemBuilder: (context, index) {
                        final p = payments[index];
                        return ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: CircleAvatar(
                            backgroundColor: Colors.green.shade100,
                            child: Icon(Icons.check, color: Colors.green.shade800),
                          ),
                          title: Text('K ${p['amount']} - ${p['payment_method']}', style: const TextStyle(fontWeight: FontWeight.bold)),
                          subtitle: Text('Date: ${p['received_at']?.toString().split('T')[0] ?? 'Unknown'}'),
                        );
                      },
                    ),
            ],
          ),
        ),
      ),
    );
  }
}
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:image_picker/image_picker.dart';
import 'services/api_client.dart';
import 'services/local_db.dart';
import 'services/loan_service.dart';
import 'services/sync_service.dart';
import 'services/user_session.dart';
import 'package:hive_flutter/hive_flutter.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await LocalDB.init(); 
  
  runApp(
    MultiProvider(
      providers: [
        Provider(create: (_) => ApiClient()),
        ProxyProvider<ApiClient, SyncService>(
          update: (_, apiClient, __) => SyncService(apiClient),
        ),
        ProxyProvider<ApiClient, LoanService>(
          update: (_, apiClient, __) => LoanService(apiClient),
        ),
      ],
      child: const NimbusApp(),
    ),
  );
}

class NimbusApp extends StatelessWidget {
  const NimbusApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Nimbus Field',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        primarySwatch: Colors.orange,
        scaffoldBackgroundColor: const Color(0xFFF7F5F0),
        appBarTheme: const AppBarTheme(
          backgroundColor: Colors.white,
          foregroundColor: Colors.black,
          elevation: 0,
        ),
        inputDecorationTheme: const InputDecorationTheme(
          filled: true,
          fillColor: Colors.white,
          border: OutlineInputBorder(),
        ),
      ),
      home: const LoginScreen(),
    );
  }
}

// ==========================================
// LOGIN SCREEN
// ==========================================
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isLoading = false;

  void _login() async {
    if (_usernameController.text.isEmpty || _passwordController.text.isEmpty) return;
    
    setState(() => _isLoading = true);
    final api = context.read<ApiClient>();
    
    final success = await api.login(_usernameController.text.trim(), _passwordController.text);
    
    setState(() => _isLoading = false);
    
    if (success) {
      if (mounted) {
        Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const DashboardScreen()));
      }
    } else {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Invalid username or password'), backgroundColor: Colors.red),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.account_balance, size: 80, color: Colors.orange),
            const SizedBox(height: 40),
            TextField(
              controller: _usernameController, 
              decoration: const InputDecoration(labelText: 'Username')
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _passwordController, 
              decoration: const InputDecoration(labelText: 'Password'), 
              obscureText: true
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              height: 50,
              child: ElevatedButton(
                onPressed: _isLoading ? null : _login,
                child: _isLoading 
                  ? const CircularProgressIndicator(color: Colors.white) 
                  : const Text('Log In', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ==========================================
// DASHBOARD / CLIENT PORTFOLIO
// ==========================================
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});
  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<LoanService>().syncLoansFromServer().then((_) {
        if (mounted) setState(() {}); 
      });
    });
  }

  void _syncAll() async {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Syncing data...')));
    await context.read<SyncService>().syncOfflinePayments();
    await context.read<LoanService>().syncLoansFromServer();
    if (mounted) {
      setState(() {});
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Sync complete!')));
    }
  }

  Widget _buildKpiCard(String title, String value, IconData icon, Color color) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.grey.shade300),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 28),
            const SizedBox(height: 12),
            Text(title, style: const TextStyle(fontSize: 12, color: Colors.grey, fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            Text(value, style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: color)),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(UserSession.organizationName, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
            Text('${UserSession.branchName} • ${UserSession.officerName}', style: const TextStyle(fontSize: 12, color: Colors.grey)),
          ],
        ),
        actions: [
          IconButton(icon: const Icon(Icons.sync), onPressed: _syncAll, tooltip: 'Sync Data'),
          IconButton(
            icon: const Icon(Icons.logout), 
            onPressed: () async {
              await context.read<ApiClient>().logout();
              if (context.mounted) {
                Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const LoginScreen()));
              }
            }
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          await Navigator.push(
            context, 
            MaterialPageRoute(builder: (_) => const LoanApplicationScreen())
          );
          if (mounted) setState(() {});
        },
        backgroundColor: Colors.orange,
        icon: const Icon(Icons.person_add, color: Colors.white),
        label: const Text('New Application', style: TextStyle(color: Colors.white)),
      ),
      body: ValueListenableBuilder<Box>(
        valueListenable: Hive.box('offline_loans').listenable(),
        builder: (context, Box box, _) {
          final allLoans = box.values.map((e) => Map<String, dynamic>.from(e as Map)).toList();
          
          final activeLoans = allLoans.where((l) {
            final balance = double.tryParse(l['balance_due']?.toString() ?? '0') ?? 0.0;
            return balance > 0;
          }).toList();

          double totalPortfolio = 0;
          int overdueCount = 0;

          for (var loan in activeLoans) {
            totalPortfolio += double.tryParse(loan['balance_due']?.toString() ?? '0') ?? 0.0;
            final dpd = loan['days_past_due'] ?? 0;
            if (dpd > 0) overdueCount++;
          }

          final filteredLoans = activeLoans.where((l) {
            final clientName = (l['client_name'] ?? '').toString().toLowerCase();
            final loanNumber = (l['loan_number'] ?? '').toString().toLowerCase();
            return clientName.contains(_searchQuery) || loanNumber.contains(_searchQuery);
          }).toList();

          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                child: Row(
                  children: [
                    _buildKpiCard('PORTFOLIO', 'K ${totalPortfolio.toStringAsFixed(0)}', Icons.account_balance_wallet, Colors.blue.shade700),
                    const SizedBox(width: 12),
                    _buildKpiCard('OVERDUE', '$overdueCount Loans', Icons.warning_amber_rounded, Colors.red.shade700),
                  ],
                ),
              ),
              ValueListenableBuilder<Box>(
                valueListenable: Hive.box('offline_payments').listenable(),
                builder: (context, Box payBox, _) {
                  final unsynced = payBox.values.where((e) => e['synced'] == false).length;
                  if (unsynced == 0) return const SizedBox.shrink();
                  return Container(
                    width: double.infinity,
                    color: Colors.orange.shade100,
                    padding: const EdgeInsets.all(8),
                    child: Text(
                      'You have $unsynced unsynced payments. Tap Sync.', 
                      textAlign: TextAlign.center, 
                      style: TextStyle(color: Colors.orange.shade900, fontSize: 12, fontWeight: FontWeight.bold)
                    ),
                  );
                },
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                child: TextField(
                  decoration: InputDecoration(
                    hintText: 'Search client or loan number...',
                    prefixIcon: const Icon(Icons.search),
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
                  ),
                  onChanged: (val) => setState(() => _searchQuery = val.toLowerCase()),
                ),
              ),
              Expanded(
                child: filteredLoans.isEmpty 
                  ? const Center(child: Text('No active loans found. Tap Sync to fetch.', style: TextStyle(color: Colors.grey)))
                  : ListView.builder(
                      itemCount: filteredLoans.length,
                      itemBuilder: (context, index) {
                        final loan = filteredLoans[index];
                        final dpd = loan['days_past_due'] ?? 0;
                        final isPending = loan['status'] == 'PENDING_APPROVAL';
                        
                        return Card(
                          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                          elevation: 0,
                          shape: RoundedRectangleBorder(
                            side: BorderSide(color: isPending ? Colors.orange.shade300 : Colors.grey.shade300),
                            borderRadius: BorderRadius.circular(12)
                          ),
                          child: ListTile(
                            onTap: () {
                              Navigator.push(
                                context, 
                                MaterialPageRoute(builder: (_) => LoanDetailsScreen(loan: loan))
                              );
                            },
                            title: Text(loan['client_name'] ?? 'Unknown Client', style: const TextStyle(fontWeight: FontWeight.bold)),
                            subtitle: Padding(
                              padding: const EdgeInsets.only(top: 4.0),
                              child: Text('${loan['loan_number']}\nBal: K ${loan['balance_due']} • Next: ${loan['next_due_date'] ?? 'N/A'}'),
                            ),
                            isThreeLine: true,
                            trailing: Container(
                              padding: const EdgeInsets.all(8),
                              decoration: BoxDecoration(
                                color: isPending 
                                  ? Colors.orange.shade50 
                                  : (dpd > 0 ? Colors.red.shade50 : Colors.green.shade50),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                isPending 
                                  ? 'Pending Approval'
                                  : (dpd > 0 ? '$dpd DPD' : 'Current'),
                                style: TextStyle(
                                  color: isPending 
                                    ? Colors.orange.shade800
                                    : (dpd > 0 ? Colors.red : Colors.green), 
                                  fontWeight: FontWeight.bold
                                ),
                              ),
                            ),
                          ),
                        );
                      },
                    ),
              ),
            ],
          );
        },
      ),
    );
  }
}

// ==========================================
// LOAN APPLICATION SCREEN
// ==========================================
class LoanApplicationScreen extends StatefulWidget {
  const LoanApplicationScreen({super.key});

  @override
  State<LoanApplicationScreen> createState() => _LoanApplicationScreenState();
}

class _LoanApplicationScreenState extends State<LoanApplicationScreen> {
  final _formKey = GlobalKey<FormState>();
  bool _isSaving = false;

  final ImagePicker _picker = ImagePicker();
  Uint8List? _clientImageBytes; 
  Uint8List? _nrcImageBytes; 

  // Toggle for Client Type
  bool _isNewClient = true;

  // Existing Clients Data
  List<Map<String, dynamic>> _existingClients = [];
  String? _selectedClientId;
  bool _isLoadingClients = true;

  // --- Dynamic Loan Products ---
  List<Map<String, dynamic>> _loanProducts = [];
  String? _selectedProductCode;
  bool _isLoadingProducts = true;

  // Client Details (KYC)
  final _nameController = TextEditingController();
  final _phoneController = TextEditingController();
  final _nrcController = TextEditingController();
  
  // Loan Terms
  final _amountController = TextEditingController();
  final _tenureController = TextEditingController(text: '12');
  String _repaymentFrequency = 'Monthly';
  String _selectedPurpose = 'Stock Purchase';
  final _purposeNotesController = TextEditingController();

  // Appraisal
  final _monthlyIncomeController = TextEditingController();
  final _monthlyExpensesController = TextEditingController();
  final _existingDebtsController = TextEditingController();
  final _netWorthController = TextEditingController();
  final _collateralController = TextEditingController();

  // Guarantors
  final _guarantor1Name = TextEditingController();
  final _guarantor1Phone = TextEditingController();
  final _guarantor1Nrc = TextEditingController();
  final _guarantor1Relationship = TextEditingController();

  final _guarantor2Name = TextEditingController();
  final _guarantor2Phone = TextEditingController();
  final _guarantor2Nrc = TextEditingController();
  final _guarantor2Relationship = TextEditingController();

  @override
  void initState() {
    super.initState();
    _fetchInitialData();
  }

  Future<void> _fetchInitialData() async {
    final api = context.read<ApiClient>();
    
    // Fetch products and clients sequentially to avoid Future.wait type inference issues
    final products = await api.getLoanProducts();
    final clients = await api.getClients();

    if (mounted) {
      setState(() {
        // 1. Setup Loan Products
        _loanProducts = products;
        _isLoadingProducts = false;
        if (_loanProducts.isNotEmpty) {
          _selectedProductCode = _loanProducts.first['code'];
        }

        // 2. Setup Existing Clients
        _existingClients = clients;
        _isLoadingClients = false;
      });
    }
  }

  Future<void> _pickImage(ImageSource source, bool isNrc) async {
    try {
      final XFile? pickedFile = await _picker.pickImage(
        source: source,
        maxWidth: 800,
        imageQuality: 80,
      );

      if (pickedFile != null) {
        final bytes = await pickedFile.readAsBytes();
        setState(() {
          if (isNrc) {
            _nrcImageBytes = bytes;
          } else {
            _clientImageBytes = bytes;
          }
        });
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error picking image: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  void _showImageSourceDialog(bool isNrc) {
    showModalBottomSheet(
      context: context,
      builder: (_) => SafeArea(
        child: Wrap(
          children: [
            ListTile(
              leading: const Icon(Icons.camera_alt, color: Colors.orange),
              title: const Text('Take a Photo'),
              onTap: () {
                Navigator.pop(context);
                _pickImage(ImageSource.camera, isNrc);
              },
            ),
            ListTile(
              leading: const Icon(Icons.photo_library, color: Colors.orange),
              title: const Text('Choose from Gallery'),
              onTap: () {
                Navigator.pop(context);
                _pickImage(ImageSource.gallery, isNrc);
              },
            ),
          ],
        ),
      ),
    );
  }

  void _submitApplication() async {
    if (!_formKey.currentState!.validate()) return;

    // If new client, require photos
    if (_isNewClient) {
      if (_clientImageBytes == null || _nrcImageBytes == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Please capture both Client Photo and NRC Photo for KYC.'), backgroundColor: Colors.red),
        );
        return;
      }
    }
    
    setState(() => _isSaving = true);

    // Get client details
    String clientName = _nameController.text;
    String clientNrc = _nrcController.text;
    String clientPhone = _phoneController.text;

    if (!_isNewClient && _selectedClientId != null) {
      final existing = _existingClients.firstWhere((c) => c['id'] == _selectedClientId);
      clientName = "${existing['first_name']} ${existing['last_name']}";
      clientNrc = existing['nrc'] ?? '';
      clientPhone = existing['phone'] ?? '';
    }

    final newLoan = {
      'id': DateTime.now().millisecondsSinceEpoch,
      'is_new_client': _isNewClient,
      'client_id': _isNewClient ? null : _selectedClientId,
      'client_name': clientName,
      'phone': clientPhone,
      'nrc': clientNrc,
      'client_photo': _clientImageBytes,
      'nrc_photo': _nrcImageBytes, 
      'loan_number': 'LN-NEW-${DateTime.now().millisecondsSinceEpoch.toString().substring(8)}',
      'product_code': _selectedProductCode,
      'balance_due': _amountController.text,
      'next_due_amount': _amountController.text,
      'next_due_date': 'Pending Approval',
      'tenure_months': _tenureController.text,
      'repayment_frequency': _repaymentFrequency,
      'purpose': _selectedPurpose,
      'purpose_notes': _purposeNotesController.text,
      'monthly_income': _monthlyIncomeController.text,
      'monthly_expenses': _monthlyExpensesController.text,
      'existing_debts': _existingDebtsController.text,
      'net_worth': _netWorthController.text,
      'collateral': _collateralController.text,
      // Guarantor 1
      'guarantor1_name': _guarantor1Name.text,
      'guarantor1_phone': _guarantor1Phone.text,
      'guarantor1_nrc': _guarantor1Nrc.text,
      'guarantor1_relationship': _guarantor1Relationship.text,
      // Guarantor 2
      'guarantor2_name': _guarantor2Name.text,
      'guarantor2_phone': _guarantor2Phone.text,
      'guarantor2_nrc': _guarantor2Nrc.text,
      'guarantor2_relationship': _guarantor2Relationship.text,
      
      'days_past_due': 0,
      'status': 'PENDING_APPROVAL',
      'branch': UserSession.branchName, 
      'officer': UserSession.officerName,
      'created_at': DateTime.now().toIso8601String(),
    };
    
    await Hive.box('offline_loans').add(newLoan);
    
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Application saved! Sent for Branch Manager approval.'), backgroundColor: Colors.green)
      );
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('New Application'),
      ),
      body: Form(
        key: _formKey,
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // --- CLIENT TYPE TOGGLE ---
              SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(value: true, label: Text('New Client'), icon: Icon(Icons.person_add)),
                  ButtonSegment(value: false, label: Text('Existing Client'), icon: Icon(Icons.person_search)),
                ],
                selected: {_isNewClient},
                onSelectionChanged: (Set<bool> newSelection) {
                  setState(() => _isNewClient = newSelection.first);
                },
                style: ButtonStyle(
                  backgroundColor: MaterialStateProperty.resolveWith<Color>(
                    (Set<MaterialState> states) {
                      if (states.contains(MaterialState.selected)) {
                        return Colors.orange.shade100;
                      }
                      return Colors.white;
                    },
                  ),
                ),
              ),
              const SizedBox(height: 24),

              // --- APPLICANT & KYC ---
              _buildSectionTitle('Applicant Details'),
              
              // IF EXISTING CLIENT: Dropdown
              if (!_isNewClient) 
                _isLoadingClients 
                  ? const Center(child: CircularProgressIndicator())
                  : DropdownButtonFormField<String>(
                      value: _selectedClientId,
                      decoration: const InputDecoration(labelText: 'Select Existing Client'),
                      items: _existingClients.map((c) {
                        final name = "${c['first_name']} ${c['last_name']}";
                        final nrc = c['nrc'] ?? 'No NRC';
                        return DropdownMenuItem<String>(
                          value: c['id'],
                          child: Text('$name — $nrc', overflow: TextOverflow.ellipsis),
                        );
                      }).toList(),
                      onChanged: (v) => setState(() => _selectedClientId = v),
                      validator: (v) => v == null ? 'Required' : null,
                    ),

              // IF NEW CLIENT: Text fields and Photos
              if (_isNewClient) ...[
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    GestureDetector(
                      onTap: () => _showImageSourceDialog(false),
                      child: Container(
                        width: 140, height: 140,
                        decoration: BoxDecoration(
                          color: Colors.grey.shade200,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: Colors.grey.shade400),
                          image: _clientImageBytes != null
                              ? DecorationImage(image: MemoryImage(_clientImageBytes!), fit: BoxFit.cover)
                              : null,
                        ),
                        child: _clientImageBytes == null
                            ? const Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Icon(Icons.add_a_photo, size: 40, color: Colors.grey),
                                  SizedBox(height: 8),
                                  Text('Client Photo', style: TextStyle(fontSize: 12, color: Colors.grey)),
                                ],
                              )
                            : null,
                      ),
                    ),
                    GestureDetector(
                      onTap: () => _showImageSourceDialog(true),
                      child: Container(
                        width: 140, height: 140,
                        decoration: BoxDecoration(
                          color: Colors.grey.shade200,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: Colors.grey.shade400),
                          image: _nrcImageBytes != null
                              ? DecorationImage(image: MemoryImage(_nrcImageBytes!), fit: BoxFit.cover)
                              : null,
                        ),
                        child: _nrcImageBytes == null
                            ? const Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Icon(Icons.badge, size: 40, color: Colors.grey),
                                  SizedBox(height: 8),
                                  Text('NRC Photo', style: TextStyle(fontSize: 12, color: Colors.grey)),
                                ],
                              )
                            : null,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _nameController,
                  decoration: const InputDecoration(labelText: 'Client Full Name'),
                  validator: (v) => v!.isEmpty ? 'Required' : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _phoneController,
                  keyboardType: TextInputType.phone,
                  decoration: const InputDecoration(labelText: 'Phone Number (Customer Portal)'),
                  validator: (v) => v!.isEmpty ? 'Required' : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _nrcController,
                  decoration: const InputDecoration(labelText: 'National ID / NRC Number'),
                  validator: (v) => v!.isEmpty ? 'Required for KYC' : null,
                ),
              ],
              
              const SizedBox(height: 24),

              // --- REQUESTED TERMS ---
              _buildSectionTitle('Requested Terms'),
              _isLoadingProducts 
                ? const Center(child: CircularProgressIndicator())
                : DropdownButtonFormField<String>(
                    value: _selectedProductCode,
                    decoration: const InputDecoration(labelText: 'Loan Product'),
                    items: _loanProducts.map((p) => DropdownMenuItem<String>(
                      value: p['code'],
                      child: Text('${p['code']} — ${p['name']}', overflow: TextOverflow.ellipsis),
                    )).toList(),
                    onChanged: (v) => setState(() => _selectedProductCode = v),
                    validator: (v) => v == null ? 'Required' : null,
                  ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _amountController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Amount (ZMW)'),
                validator: (v) => v!.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _tenureController,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(labelText: 'Tenure (Months)'),
                      validator: (v) => v!.isEmpty ? 'Required' : null,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      value: _repaymentFrequency,
                      decoration: const InputDecoration(labelText: 'Frequency'),
                      items: ['Monthly', 'Bi-Weekly', 'Weekly']
                          .map((e) => DropdownMenuItem(value: e, child: Text(e))).toList(),
                      onChanged: (v) => setState(() => _repaymentFrequency = v!),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: _selectedPurpose,
                decoration: const InputDecoration(labelText: 'Purpose'),
                items: ['Stock Purchase', 'Business Capital', 'Equipment', 'Emergency']
                    .map((e) => DropdownMenuItem(value: e, child: Text(e))).toList(),
                onChanged: (v) => setState(() => _selectedPurpose = v!),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _purposeNotesController,
                decoration: const InputDecoration(labelText: 'Purpose notes (Brief description)'),
              ),
              const SizedBox(height: 24),

              // --- APPRAISAL ---
              _buildSectionTitle('Appraisal'),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _monthlyIncomeController,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      decoration: const InputDecoration(labelText: 'Monthly Income'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextFormField(
                      controller: _monthlyExpensesController,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      decoration: const InputDecoration(labelText: 'Monthly Expenses'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _existingDebtsController,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      decoration: const InputDecoration(labelText: 'Existing Debts'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextFormField(
                      controller: _netWorthController,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      decoration: const InputDecoration(labelText: 'Net Worth'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _collateralController,
                maxLines: 2,
                decoration: const InputDecoration(
                  labelText: 'Collateral summary',
                  hintText: 'e.g. Toyota Hilux 2018, valued at K85,000',
                ),
              ),
              const SizedBox(height: 24),

              // --- GUARANTORS ---
              _buildSectionTitle('Guarantor 1'),
              TextFormField(
                controller: _guarantor1Name,
                decoration: const InputDecoration(labelText: 'Full Name'),
                validator: (v) => v!.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _guarantor1Phone,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(labelText: 'Phone Number'),
                validator: (v) => v!.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _guarantor1Nrc,
                decoration: const InputDecoration(labelText: 'National ID / NRC'),
                validator: (v) => v!.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _guarantor1Relationship,
                decoration: const InputDecoration(labelText: 'Relationship to Client (e.g. Spouse, Friend)'),
                validator: (v) => v!.isEmpty ? 'Required' : null,
              ),

              const SizedBox(height: 24),
              _buildSectionTitle('Guarantor 2'),
              TextFormField(
                controller: _guarantor2Name,
                decoration: const InputDecoration(labelText: 'Full Name'),
                validator: (v) => v!.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _guarantor2Phone,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(labelText: 'Phone Number'),
                validator: (v) => v!.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _guarantor2Nrc,
                decoration: const InputDecoration(labelText: 'National ID / NRC'),
                validator: (v) => v!.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _guarantor2Relationship,
                decoration: const InputDecoration(labelText: 'Relationship to Client (e.g. Spouse, Friend)'),
                validator: (v) => v!.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 32),

              // --- SUBMIT ---
              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton(
                  onPressed: _isSaving ? null : _submitApplication,
                  child: _isSaving 
                    ? const CircularProgressIndicator(color: Colors.white) 
                    : const Text('Submit Application', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                ),
              ),
              const SizedBox(height: 32),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSectionTitle(String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12.0),
      child: Text(
        title,
        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.orange),
      ),
    );
  }
}

// ==========================================
// LOAN DETAILS SCREEN
// ==========================================
class LoanDetailsScreen extends StatelessWidget {
  final Map<String, dynamic> loan;
  const LoanDetailsScreen({super.key, required this.loan});

  void _openPaymentModal(BuildContext context) {
    final amountController = TextEditingController(text: loan['next_due_amount']?.toString() ?? '');
    bool isSaving = false;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            return Padding(
              padding: EdgeInsets.only(
                bottom: MediaQuery.of(context).viewInsets.bottom, 
                left: 16, right: 16, top: 24
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('Record Payment', style: Theme.of(context).textTheme.headlineSmall),
                  const SizedBox(height: 8),
                  Text('${loan['client_name']} • ${loan['loan_number']}', style: const TextStyle(color: Colors.grey)),
                  const SizedBox(height: 16),
                  Text('Outstanding Balance: K ${loan['balance_due']}', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.red)),
                  const SizedBox(height: 16),
                  TextField(
                    controller: amountController,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Amount (ZMW)'),
                  ),
                  const SizedBox(height: 24),
                  SizedBox(
                    height: 50,
                    child: ElevatedButton(
                      onPressed: isSaving ? null : () async {
                        if (amountController.text.isEmpty) return;
                        setModalState(() => isSaving = true);

                        final paymentData = {
                          'loan': loan['id'],
                          'loan_number': loan['loan_number'],
                          'amount': amountController.text,
                          'payment_method': 'CASH',
                          'payment_type': 'INSTALLMENT',
                          'transaction_ref': 'FIELD-${DateTime.now().millisecondsSinceEpoch}',
                          'notes': 'Recorded via Field App',
                          'synced': false,
                          'date': DateTime.now().toIso8601String(),
                        };

                        await LocalDB.saveOfflinePayment(paymentData);
                        
                        if (context.mounted) Navigator.pop(context);
                        if (context.mounted) Navigator.pop(context);
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Payment saved locally! Sync to push to server.'), backgroundColor: Colors.green)
                          );
                        }
                      },
                      child: isSaving ? const CircularProgressIndicator(color: Colors.white) : const Text('Save Payment', style: TextStyle(fontSize: 16)),
                    ),
                  ),
                  const SizedBox(height: 24),
                ],
              ),
            );
          }
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final isPending = loan['status'] == 'PENDING_APPROVAL';
    final rawBranch = loan['branch']?.toString() ?? 'N/A';
    final friendlyBranch = UserSession.getFriendlyBranchName(rawBranch);
    
    final Uint8List? clientPhotoBytes = loan['client_photo']; 
    final Uint8List? nrcPhotoBytes = loan['nrc_photo'];
    
    return Scaffold(
      appBar: AppBar(
        title: const Text('Loan Details'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Card(
              elevation: 0,
              shape: RoundedRectangleBorder(side: BorderSide(color: Colors.grey.shade300), borderRadius: BorderRadius.circular(12)),
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        if (clientPhotoBytes != null)
                          Container(
                            width: 60, height: 60,
                            margin: const EdgeInsets.only(right: 16),
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              image: DecorationImage(image: MemoryImage(clientPhotoBytes), fit: BoxFit.cover),
                            ),
                          ),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(loan['client_name'] ?? 'Unknown', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                              const SizedBox(height: 4),
                              Text('Loan: ${loan['loan_number']}', style: const TextStyle(color: Colors.grey)),
                              if (loan['nrc'] != null && loan['nrc'].toString().isNotEmpty)
                                Text('NRC: ${loan['nrc']}', style: const TextStyle(color: Colors.grey)),
                            ],
                          ),
                        ),
                      ],
                    ),
                    
                    // NRC Photo Display
                    if (nrcPhotoBytes != null) ...[
                      const SizedBox(height: 16),
                      const Text('NRC Document:', style: TextStyle(fontSize: 12, color: Colors.grey, fontWeight: FontWeight.bold)),
                      const SizedBox(height: 8),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: Image.memory(nrcPhotoBytes, height: 120, fit: BoxFit.cover),
                      ),
                    ],
                    
                    const Divider(height: 24),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        _buildInfoRow('Branch', friendlyBranch),
                        _buildInfoRow('Officer', loan['officer'] ?? 'N/A'),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        _buildInfoRow('Balance Due', 'K ${loan['balance_due']}', isHighlight: true),
                        _buildInfoRow('Status', isPending ? 'Pending Approval' : 'Active', isHighlight: isPending),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            
            const SizedBox(height: 24),
            const Text('Repayment History', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            
            ValueListenableBuilder<Box>(
              valueListenable: Hive.box('offline_payments').listenable(),
              builder: (context, Box box, _) {
                final payments = box.values
                  .map((e) => Map<String, dynamic>.from(e as Map))
                  .where((p) => p['loan'] == loan['id'] || p['loan_number'] == loan['loan_number'])
                  .toList();
                  
                if (payments.isEmpty) {
                  return const Center(child: Padding(
                    padding: EdgeInsets.all(24.0),
                    child: Text('No repayments recorded yet.', style: TextStyle(color: Colors.grey)),
                  ));
                }

                return ListView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: payments.length,
                  itemBuilder: (context, index) {
                    final payment = payments[index];
                    return ListTile(
                      leading: const CircleAvatar(
                        backgroundColor: Colors.green,
                        child: Icon(Icons.check, color: Colors.white, size: 20),
                      ),
                      title: Text('K ${payment['amount']} - ${payment['payment_method']}'),
                      subtitle: Text(payment['date']?.toString().split('T')[0] ?? 'Unknown Date'),
                      trailing: Text(
                        payment['synced'] == true ? 'Synced' : 'Pending Sync',
                        style: TextStyle(
                          color: payment['synced'] == true ? Colors.green : Colors.orange,
                          fontWeight: FontWeight.bold,
                          fontSize: 12
                        ),
                      ),
                    );
                  },
                );
              },
            ),
            
            const SizedBox(height: 32),
            
            if (isPending)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.orange.shade50,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.orange.shade300)
                ),
                child: const Text(
                  'This loan is awaiting approval from the Branch Manager. Payments cannot be recorded until it is disbursed.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.orange, fontWeight: FontWeight.bold),
                ),
              )
            else
              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton.icon(
                  icon: const Icon(Icons.payment),
                  label: const Text('Record Payment', style: TextStyle(fontSize: 16)),
                  onPressed: () => _openPaymentModal(context),
                ),
              ),
            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String label, String value, {bool isHighlight = false}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
        const SizedBox(height: 2),
        Text(
          value, 
          style: TextStyle(
            fontSize: 16, 
            fontWeight: FontWeight.bold,
            color: isHighlight ? Colors.orange.shade800 : Colors.black87
          )
        ),
      ],
    );
  }
}